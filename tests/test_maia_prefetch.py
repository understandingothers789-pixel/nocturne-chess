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

    def test_configured_range_limits_foreground_and_prefetch_requests(self):
        self.assertEqual(RATINGS[0], 600)
        with tempfile.TemporaryDirectory() as folder:
            c = MaiaController(folder)
            c.set_rating_range(1200, 2000)
            c.request('root', [], 1800, sweep=True)
            self.assertEqual(set(c._queued[1]['ratings']), {1200, 1400, 1600, 1800, 2000})
            c._queued = None
            c.debounce.stop()
            c._ready = True
            c.device_label = 'AMD ROCm'
            c.prefetch('root', [['e2e4']], 1800)
            with patch.object(c.process, 'write') as write:
                c._prefetch_next()
                request = json.loads(bytes(write.call_args.args[0]))
                self.assertTrue(set(request['ratings']) <= set(c.ratings))
            c.set_rating_range(1400, 1800)
            self.assertIsNone(c._prefetch_active)
            self.assertFalse(c.prefetch_queue)
            with self.assertRaises(ValueError):
                c.request('root', [], 1000, sweep=True)
            c.stop()

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

    def test_quick_return_to_running_position_replaces_intermediate_request(self):
        with tempfile.TemporaryDirectory() as folder:
            c = MaiaController(folder)
            c.request('root', ['e2e4'], 1800)
            c._active, c._queued = c._queued, None
            c._busy = True
            c.request('root', ['d2d4'], 1800)
            c.request('root', ['e2e4'], 1800)
            self.assertEqual(c._queued[1]['moves'], ['e2e4'])
            self.assertEqual(c._queued[1]['id'], c._serial)
            c.stop()

    def test_failed_current_request_can_be_retried(self):
        with tempfile.TemporaryDirectory() as folder:
            c = MaiaController(folder)
            c.request('root', [], 1800)
            c._active, c._queued = c._queued, None
            old = c._serial
            c._busy = False
            c.request('root', [], 1800)
            self.assertGreater(c._serial, old)
            self.assertIsNotNone(c._queued)
            c.stop()

    def test_prefetch_is_lazy_and_skips_cached_work_in_bounded_ticks(self):
        with tempfile.TemporaryDirectory() as folder:
            c = MaiaController(folder)
            consumed = []
            def positions():
                for i in range(100):
                    consumed.append(i)
                    yield [str(i)]
            c.prefetch('root', positions(), 1800)
            self.assertEqual(consumed, [])
            c._ready = True
            c.device_label = 'NVIDIA CUDA'
            for i in range(100):
                key = c.position_key('root', [str(i)])
                c.cache[key] = {str(r): {} for r in RATINGS}
                c.value_cache[key] = {str(r): [0, 1, 0] for r in RATINGS}
            c._prefetch_next()
            self.assertEqual(len(consumed), 8)
            c.stop()

    def test_background_persistence_is_batched_and_cpu_retry_drops_partial_output(self):
        with tempfile.TemporaryDirectory() as folder:
            c = MaiaController(folder)
            c._prefetch_active = (-1, 'key')
            message = {'id': -1, 'complete': True, 'policies': {'1800': {}}}
            with patch.object(c.process, 'readAllStandardOutput', return_value=QByteArray((json.dumps(message)+'\n').encode())), patch.object(c, '_save_cache') as save:
                c._read()
                save.assert_not_called()
                self.assertTrue(c.cache_timer.isActive())
            c._buffer = b'{"unfinished":'
            c._external = True
            c._prefetch_active = (-2, 'other')
            self.assertTrue(c._retry_cpu())
            self.assertEqual(c._buffer, b'')
            self.assertIsNone(c._prefetch_active)
            c.stop()

    def test_foreground_completion_defers_disk_write_and_flushes_on_stop(self):
        with tempfile.TemporaryDirectory() as folder:
            c = MaiaController(folder)
            c.request('root', [], 1800)
            c._active, c._queued = c._queued, None
            c._busy = True
            message = {'id': c._serial, 'complete': True,
                       'policies': {'1800': {'e2e4': 1.0}}, 'outcomes': {'1800': [.4, .2, .4]}}
            with patch.object(c.process, 'readAllStandardOutput', return_value=QByteArray((json.dumps(message)+'\n').encode())), patch.object(c, '_save_cache', wraps=c._save_cache) as save:
                c._read()
                save.assert_not_called()
                self.assertTrue(c.cache_timer.isActive())
                self.assertEqual(c.policies['1800']['e2e4'], 1.0)
                c.stop()
                save.assert_called_once()
                self.assertTrue(c.cache_path.exists())
