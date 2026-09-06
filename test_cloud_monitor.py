import importlib.util, unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path

spec=importlib.util.spec_from_file_location('m',Path(__file__).with_name('cloud_monitor.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class ReminderTests(unittest.TestCase):
    def item(self,hours=160,state='unsubmitted'):
        due=(datetime.now(timezone.utc)+timedelta(hours=hours)).isoformat()
        return {'kind':'assignment','due_at':due,'submission_state':state}
    def test_thresholds(self):
        self.assertEqual(m.reminder_threshold(self.item(160),{}),7)
        self.assertEqual(m.reminder_threshold(self.item(90),{'7':{'complete':True}}),4)
        self.assertEqual(m.reminder_threshold(self.item(40),{'7':{'complete':True},'4':{'complete':True}}),2)
        self.assertEqual(m.reminder_threshold(self.item(20),{'7':{'complete':True},'4':{'complete':True},'2':{'complete':True}}),1)
    def test_incomplete_delivery_retries_same_threshold(self):
        self.assertEqual(m.reminder_threshold(self.item(90),{'7':{'discord':'sent','complete':False}}),7)
    def test_no_catchup_spam(self): self.assertEqual(m.reminder_threshold(self.item(20),{}),1)
    def test_submitted_and_expired(self):
        self.assertIsNone(m.reminder_threshold(self.item(20,'submitted'),{}))
        self.assertIsNone(m.reminder_threshold(self.item(-1),{}))

if __name__=='__main__':unittest.main()
