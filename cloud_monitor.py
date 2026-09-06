import hashlib, html, json, os, re, smtplib, ssl, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage
from pathlib import Path

BASE='https://ccanvas.joongbu.ac.kr'
STATE=Path('state.json')
KST=timezone(timedelta(hours=9))

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args): return None

def get(url, token):
    full=urllib.parse.urljoin(BASE,url)
    p=urllib.parse.urlsplit(full)
    if p.scheme!='https' or p.netloc!='ccanvas.joongbu.ac.kr' or not p.path.startswith('/api/v1/'):
        raise RuntimeError('unsafe destination')
    req=urllib.request.Request(full,headers={'Authorization':'Bearer '+token,'Accept':'application/json'})
    with urllib.request.build_opener(NoRedirect()).open(req,timeout=30) as r:
        return json.loads(r.read(20_000_000)),r.headers.get('Link','')

def listing(path,token):
    url=path+('&' if '?' in path else '?')+'per_page=100'; out=[]; seen=set()
    while url:
        if url in seen or len(seen)>100: raise RuntimeError('pagination failed')
        seen.add(url); rows,links=get(url,token)
        if not isinstance(rows,list): raise RuntimeError('unexpected response')
        out+=rows
        m=re.search(r'<([^>]+)>;\s*rel="next"',links); url=m.group(1) if m else None
    return out

def text(raw):
    raw=re.sub(r'<(script|style)\b[^>]*>.*?</\1>','',raw or '',flags=re.S|re.I)
    raw=re.sub(r'<(?:br\s*/?|/p|/div|/li)>','\n',raw,flags=re.I)
    return re.sub(r'\n{3,}','\n\n',html.unescape(re.sub('<[^>]+>','',raw))).strip()

def clean_url(value):
    p=urllib.parse.urlsplit(urllib.parse.urljoin(BASE,value or ''))
    return urllib.parse.urlunsplit((p.scheme,p.netloc,p.path,'',''))

def fingerprint(item):
    keep={k:item.get(k) for k in ('kind','course_id','id','title','body','due_at','lock_at','submission_types')}
    return hashlib.sha256(json.dumps(keep,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def collect(token):
    courses=listing('/api/v1/courses?enrollment_state=active&include[]=term',token)
    items=[]; errors=[]
    for c in courses:
        if c.get('workflow_state')!='available': continue
        cid=c['id']
        for kind,path in [('announcement',f'/api/v1/courses/{cid}/discussion_topics?only_announcements=true'),('assignment',f'/api/v1/courses/{cid}/assignments?include[]=submission')]:
            try: rows=listing(path,token)
            except Exception as e: errors.append(f'{cid}:{kind}:{type(e).__name__}'); continue
            for r in rows:
                submission=r.get('submission') or {}
                item={'kind':kind,'course_id':cid,'course':c.get('name','과목'),'id':str(r['id']),'title':r.get('title') or r.get('name') or '',
                      'body':text(r.get('message') or r.get('description') or ''),'due_at':r.get('due_at'),'lock_at':r.get('lock_at'),
                      'submission_types':r.get('submission_types',[]),'submission_state':submission.get('workflow_state'),
                      'url':clean_url(r.get('html_url') or f'{BASE}/courses/{cid}')}
                item['fingerprint']=fingerprint(item); items.append(item)
    if not courses or len(errors)>=2*len(courses): raise RuntimeError('LMS collection failed')
    return items,errors

def format_due(value):
    if not value:return '기한 미지정'
    return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(KST).strftime('%m월 %d일 %H:%M')

def message(item,change):
    kind='공지' if item['kind']=='announcement' else '과제/평가'
    body=re.sub(r'\s+',' ',item['body'])[:650]
    state=' (제출됨)' if item.get('submission_state')=='submitted' else ''
    return f"[{item['course']}] {kind} {'수정' if change=='updated' else '새 등록'}\n{item['title']}{state}\n기한: {format_due(item.get('due_at'))}\n{body or '본문 없음 — 원문 확인 필요'}\n{item['url']}"

def discord(webhook,content):
    if not webhook:return None
    if not re.fullmatch(r'https://discord\.com/api/webhooks/\d+/[A-Za-z0-9_-]+',webhook): raise RuntimeError('invalid webhook')
    body=json.dumps({'content':content[:2000],'username':'중부대 LMS 알림','allowed_mentions':{'parse':[]}},ensure_ascii=False).encode()
    req=urllib.request.Request(webhook+'?wait=true',data=body,headers={'Content-Type':'application/json','User-Agent':'JoongbuLMSMonitor/1.0'},method='POST')
    with urllib.request.build_opener(NoRedirect()).open(req,timeout=30) as r:return json.loads(r.read())['id']

def email_send(user,password,content):
    if not user or not password:return None
    msg=EmailMessage();msg['From']=user;msg['To']=user;msg['Subject']='[중부대 LMS] 새 공지·과제 알림';msg.set_content(content)
    with smtplib.SMTP_SSL('smtp.gmail.com',465,context=ssl.create_default_context(),timeout=30) as s:s.login(user,password);s.send_message(msg)
    return 'sent'

def main():
    token=os.environ['CANVAS_TOKEN']; webhook=os.getenv('DISCORD_WEBHOOK',''); gmail=os.getenv('GMAIL_ADDRESS',''); apppw=os.getenv('GMAIL_APP_PASSWORD','')
    if os.getenv('TEST_NOTIFICATION')=='1':
        stamp=datetime.now(KST).strftime('%Y-%m-%d %H:%M')
        content=f'☁️ 중부대 LMS 클라우드 알림 테스트 성공\nGitHub 서버에서 전송했습니다.\n확인 시각: {stamp} 한국시간\n앞으로 PC와 Codex가 꺼져 있어도 10분마다 확인합니다.'
        result={'discord':discord(webhook,content),'email':email_send(gmail,apppw,content)}
        print(json.dumps(result));return
    state=json.loads(STATE.read_text()) if STATE.exists() else {'version':1,'items':{},'deliveries':{}}
    items,errors=collect(token); first=not state['items']; alerts=[]
    current={}
    for i in items:
        key=f"{i['course_id']}:{i['kind']}:{i['id']}"; old=state['items'].get(key); current[key]=i['fingerprint']
        if not first and old!=i['fingerprint']:alerts.append((key,i,'new' if old is None else 'updated'))
    state['items']=current
    # One small monthly change keeps GitHub scheduled workflows active without a commit every 10 minutes.
    state['heartbeat_month']=datetime.now(timezone.utc).strftime('%Y-%m')
    for key,item,change in alerts:
        event=key+':'+item['fingerprint']; delivery=state['deliveries'].setdefault(event,{})
        content=message(item,change)
        if webhook and not delivery.get('discord'):delivery['discord']=discord(webhook,content)
        if gmail and apppw and not delivery.get('email'):delivery['email']=email_send(gmail,apppw,content)
        delivery['complete']=(not webhook or bool(delivery.get('discord'))) and (not(gmail and apppw) or bool(delivery.get('email')))
    state['deliveries']={k:v for k,v in state['deliveries'].items() if not v.get('complete')}
    STATE.write_text(json.dumps(state,indent=2,sort_keys=True),encoding='utf-8')
    print(json.dumps({'checked_at':datetime.now(timezone.utc).isoformat(),'courses':len({i['course_id'] for i in items}),'items':len(items),'alerts':len(alerts),'errors':errors}))

if __name__=='__main__':main()
