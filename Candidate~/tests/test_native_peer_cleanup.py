"""Native verifier shutdown ordering; test doubles, not Codex acceptance."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import asyncio
import unittest
from unittest.mock import AsyncMock
from native_approved_tasks import NativePeer, assert_denied_result

class NativePeerCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_NPC001_unsubscribe_reply_is_not_delete_receipt(self):
        events=[];receipt=asyncio.Event()
        class Input:
            def close(self):events.append('stdin_closed')
        class Process:
            stdin=Input();stdout=object();returncode=0
            stderr=type('Err',(),{'read':AsyncMock(return_value=b'')})()
            async def wait(self):events.append('process_waited')
        peer=NativePeer(Process(),'codex',[]);peer.thread='synthetic-thread'
        async def request(method,params):
            events.append('unsubscribe_reply')
            return {'status':'unsubscribed'}
        async def wait_deleted():
            events.append('waiting_delete')
            await receipt.wait()
            self.assertIn('stdin_closed',events)
            events.append('delete_confirmed')
        peer.request=request;peer.wait_deleted=wait_deleted
        task=asyncio.create_task(peer.close())
        try:
            await asyncio.sleep(0)
            self.assertIn('stdin_closed',events,'control EOF triggers native thread shutdown')
            self.assertFalse(task.done(),'control EOF must not substitute for DELETE confirmation')
            receipt.set();await task
            self.assertEqual(events,['unsubscribe_reply','stdin_closed','waiting_delete','delete_confirmed','process_waited'])
            await peer.close()
            self.assertEqual(events.count('stdin_closed'),1)
        finally:
            receipt.set()
            await task

    async def test_NPC002_missing_or_failed_delete_confirmation_stays_failed(self):
        for observer in (None,AsyncMock(side_effect=TimeoutError('synthetic missing receipt'))):
            with self.subTest(observer_missing=observer is None):
                stdin=type('Input',(),{'close':lambda self:setattr(self,'closed',True)})()
                process=type('Process',(),{'stdin':stdin,'stdout':object(),'returncode':0,
                    'stderr':type('Err',(),{'read':AsyncMock(return_value=b'')})(),
                    'wait':AsyncMock(return_value=0)})()
                peer=NativePeer(process,'codex',[]);peer.thread='synthetic-thread'
                peer.request=AsyncMock(return_value={'status':'unsubscribed'});peer.wait_deleted=observer
                with self.assertRaises(AssertionError if observer is None else TimeoutError):
                    await peer.close()
                self.assertTrue(stdin.closed)
                process.wait.assert_awaited_once()
                self.assertTrue(peer.errors.done())

    async def test_NPC003_stdio_shutdown_precedes_receipt_wait(self):
        events=[]
        class Input:
            def close(self):events.append('control_eof')
        process=type('Process',(),{'stdin':Input(),'stdout':object(),'returncode':0,
            'stderr':type('Err',(),{'read':AsyncMock(return_value=b'')})(),
            'wait':AsyncMock(return_value=0)})()
        peer=NativePeer(process,'codex',[]);peer.thread='synthetic-thread'
        peer.request=AsyncMock(return_value={'status':'unsubscribed'})
        async def receipt():
            self.assertIn('control_eof',events,'app-server must receive control EOF before native shutdown can emit DELETE')
        peer.wait_deleted=receipt
        await peer.close()
        self.assertEqual(events,['control_eof'])
        self.assertTrue(peer.close_observation['delete_confirmed'])

    def test_NPC004_native_denial_allows_null_structured_content_only_with_error(self):
        for tool in ('get_project_info','get_tags','get_layers','get_selection','get_windows','get_active_tool','get_prefab_stage','get_menu_items','manage_animation','manage_packages'):
            for value in ({'isError':True,'structuredContent':None}, {'isError':True}):
                assert_denied_result(value,tool)
            assert_denied_result({'isError':False,'structuredContent':{'success':False}},tool)
            if tool.startswith('get_'):
                assert_denied_result({'isError':False,'structuredContent':{'result':{'success':False}}},tool)
            for content in (None,{},[],{'success':True},{'result':None},{'result':{'success':True}}):
                with self.assertRaises(AssertionError):
                    assert_denied_result({'isError':False,'structuredContent':content},tool)

if __name__=='__main__':unittest.main(verbosity=2)
