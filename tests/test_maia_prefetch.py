import json
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtCore import QByteArray
from PySide6.QtWidgets import QApplication
from nocturne.maia.controller import MaiaController
from nocturne.maia import RATINGS

class PrefetchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_gpu_priority_pause_resume_and_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            c = MaiaController(folder)
            c._ready = True
            c.prefetch('root', [['e2e4']], 1800)
            with patch.object(c.process, 'write') as write:
                c.device_label = 'CPU'
                c._prefetch_next()
                write.assert_not_called()
                c.device_label = 'AMD ROCm'
                c.foreground_busy = lambda: True
                c._prefetch_next()
                write.assert_not_called()
                c.foreground_busy = lambda: False
                c._prefetch_next()
                self.assertEqual(write.call_count, 1)
                request = json.loads(bytes(write.call_args.args[0]))
                self.assertLessEqual(len(request['ratings']), 2)
                policies = c.policies.copy()
                msg = {'id':request['id'], 'complete':True, 'policies':{'1800':{'e7e5':1}}, 'outcomes':{'1800':[.4,.2,.4]}}
                with patch.object(c.process,'readAllStandardOutput',return_value=QByteArray((json.dumps(msg)+'\n').encode())):
                    c._read()
                self.assertEqual(c.policies, policies)
                key = c.position_key('root',['e2e4'])
                self.assertEqual(c.cache[key]['1800'],{'e7e5':1})
                c.cache[key] = {str(r):{} for r in RATINGS}
                c.value_cache[key] = {str(r):[0,1,0] for r in RATINGS}
                c._prefetch_next()
                self.assertEqual(write.call_count,1)
            c.stop()

    def test_foreground_discards_queue_and_stale_results(self):
        with tempfile.TemporaryDirectory() as folder:
            c = MaiaController(folder)
            c.prefetch('root',[['e2e4']],1800)
            c.request('root',[],2000)
            self.assertEqual(c.prefetch_queue,[])
            c._prefetch_active = (-1, 'old')
            c._busy = True
            msg = {'id':-1,'complete':True,'policies':{'1800':{'a2a3':1}}}
            with patch.object(c.process,'readAllStandardOutput',return_value=QByteArray((json.dumps(msg)+'\n').encode())), patch.object(c,'_dispatch') as dispatch:
                c._read()
                dispatch.assert_called_once()
            self.assertEqual(c.policies,{})
            self.assertIn('old',c.cache)
            c.stop()
