import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import review_delivery as delivery

PROJECT = 'StockTracker'
OUT = Path(__file__).resolve().parent


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        scratch = Path.cwd()/'work'/'review-delivery-tests'
        scratch.mkdir(parents=True,exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        if Path(self.temp.name).resolve().parent != scratch.resolve():
            raise ValueError('Test cleanup path escaped workspace scratch directory')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.day = '2026-10-30'
        self.review = self.root/'review.json'
        self.review.write_text(json.dumps({'review_date':self.day}),encoding='utf-8')
        self.state = self.root/'state'
        self.state.mkdir()
        delivery.write_object(self.state/(self.day+'.publication.json'), {
            'schema':'review_publication_v1','project':'CryptoTracker','review_date':self.day,
            'review_sha256':hashlib.sha256(self.review.read_bytes()).hexdigest()})

    def send(self, callback):
        return delivery.deliver_once(self.state,'CryptoTracker',self.day,self.review,callback)

    def test_provider_requires_http_and_integer_status(self):
        cases=[(200,{'status':1},'API_ACCEPTED'),(200,{'status':0},'API_NOT_ACCEPTED'),
               (200,{'status':True},'UNCONFIRMED'),(500,{'status':1},'UNCONFIRMED'),
               (200,{},'UNCONFIRMED'),(429,{'status':0},'API_NOT_ACCEPTED')]
        for http,body,expected in cases:
            with self.subTest(http=http,body=body):
                response=SimpleNamespace(status_code=http,json=lambda:body)
                self.assertEqual(delivery.provider_status(response),expected)
        response=Mock(status_code=200)
        response.json.side_effect=ValueError('sensitive provider text')
        self.assertEqual(delivery.provider_status(response),'UNCONFIRMED')

    def test_same_day_accepted_once(self):
        callback=Mock(return_value='API_ACCEPTED')
        self.assertEqual(self.send(callback),'API_ACCEPTED')
        self.assertEqual(self.send(callback),'API_ACCEPTED')
        callback.assert_called_once()
        receipt=delivery.read_object(self.state/(self.day+'.notification.json'))
        self.assertFalse(receipt['device_delivery_verified'])

    def test_timeout_is_uncertain_and_not_retried(self):
        callback=Mock(side_effect=TimeoutError('TOKEN_SECRET'))
        self.assertEqual(self.send(callback),'UNCONFIRMED')
        self.assertEqual(self.send(callback),'UNCONFIRMED')
        callback.assert_called_once()
        self.assertNotIn('TOKEN_SECRET',(self.state/(self.day+'.notification.json')).read_text())

    def test_crash_after_dispatch_intent_prevents_resend(self):
        callback=Mock(side_effect=KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt):self.send(callback)
        later=Mock(return_value='API_ACCEPTED')
        self.assertEqual(self.send(later),'UNCONFIRMED')
        later.assert_not_called()

    def test_sender_receives_the_exact_review_bound_to_publication(self):
        callback=Mock(return_value='API_ACCEPTED')
        self.send(callback)
        callback.assert_called_once_with({'review_date':self.day})

    def test_rejection_requires_operator_not_model_rerun(self):
        callback=Mock(return_value='API_NOT_ACCEPTED')
        self.assertEqual(self.send(callback),'API_NOT_ACCEPTED')
        self.assertEqual(self.send(callback),'API_NOT_ACCEPTED')
        callback.assert_called_once()

    def test_no_config_can_be_repaired_without_model_rerun(self):
        self.assertEqual(self.send(lambda review:'CONFIG_MISSING'),'CONFIG_MISSING')
        self.assertEqual(self.send(lambda review:'API_ACCEPTED'),'API_ACCEPTED')

    def test_absent_or_mismatched_publication_never_sends(self):
        path=self.state/(self.day+'.publication.json')
        path.unlink()
        callback=Mock()
        with self.assertRaises(FileNotFoundError):self.send(callback)
        delivery.write_object(path,{'schema':'review_publication_v1','project':'StockTracker'})
        with self.assertRaises(ValueError):self.send(callback)
        callback.assert_not_called()

    def test_modified_review_cannot_reuse_publication_receipt(self):
        self.review.write_text(json.dumps({'review_date':self.day,'changed':True}),encoding='utf-8')
        callback=Mock()
        with self.assertRaises(ValueError):self.send(callback)
        callback.assert_not_called()

    def test_changed_review_after_attempt_needs_reconciliation(self):
        self.send(lambda review:'API_ACCEPTED')
        self.review.write_text(json.dumps({'review_date':self.day,'changed':True}),encoding='utf-8')
        proof=delivery.read_object(self.state/(self.day+'.publication.json'))
        proof['review_sha256']=hashlib.sha256(self.review.read_bytes()).hexdigest()
        delivery.write_object(self.state/(self.day+'.publication.json'),proof)
        callback=Mock()
        with self.assertRaises(ValueError):self.send(callback)
        callback.assert_not_called()

    def test_intent_write_failure_prevents_network(self):
        callback=Mock()
        with patch.object(delivery,'write_object',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.send(callback)
        callback.assert_not_called()

    def test_concurrent_attempt_cannot_enter_locked_day(self):
        callback=Mock()
        with delivery.day_lock(self.state,self.day):
            with self.assertRaises(OSError):self.send(callback)
        callback.assert_not_called()

    def test_invalid_day_cannot_escape_state_directory(self):
        with self.assertRaises(ValueError):
            with delivery.day_lock(self.state,'../outside'):pass

    def test_crypto_day_boundaries_and_dst(self):
        for instant,allowed,blocked in [
            ('2026-10-31T06:59:59+00:00','2026-10-29','2026-10-30'),
            ('2026-10-31T07:00:00+00:00','2026-10-30','2026-10-31'),
            ('2026-11-02T07:59:59+00:00','2026-10-31','2026-11-01'),
            ('2026-11-02T08:00:00+00:00','2026-11-01','2026-11-02'),
            ('2026-03-09T06:59:59+00:00','2026-03-07','2026-03-08'),
            ('2026-03-09T07:00:00+00:00','2026-03-08','2026-03-09')]:
            now=datetime.fromisoformat(instant)
            delivery.require_completed_crypto_day(allowed,now)
            with self.assertRaises(ValueError):delivery.require_completed_crypto_day(blocked,now)

    def test_publication_no_change_is_not_remote_success(self):
        def git(root,*args):
            return {'rev-parse':'a'*40,'branch':'main','ls-remote':'b'*40+' refs/heads/main'}[args[0]]
        with patch.object(delivery,'git',side_effect=git):
            with self.assertRaises(RuntimeError):delivery.publication_proof(self.root,'StockTracker',self.day)

    def test_publication_requires_committed_dated_bytes(self):
        path=self.root/f'analysis/performance/sanitized_daily/{self.day}.json'
        path.parent.mkdir(parents=True)
        payload=json.dumps({'review_date':self.day})
        path.write_text(payload,encoding='utf-8')
        def git(root,*args):
            return {'rev-parse':'a'*40,'branch':'main','ls-remote':'a'*40+' refs/heads/main','show':payload}[args[0]]
        with patch.object(delivery,'git',side_effect=git):
            self.assertEqual(delivery.publication_proof(self.root,'StockTracker',self.day),'a'*40)
            path.write_text('{}',encoding='utf-8')
            with self.assertRaises(RuntimeError):delivery.publication_proof(self.root,'StockTracker',self.day)


def function_namespace(project,names,**values):
    path=OUT/'daily_model_review.py'
    tree=ast.parse(path.read_text(encoding='utf-8'))
    module=ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[])
    namespace=dict(values)
    exec(compile(module,str(path),'exec'),namespace)
    return namespace


class IntegrationTests(unittest.TestCase):
    def test_generation_writes_review_without_sending_for_both_projects(self):
        import argparse
        scratch=Path.cwd()/'work'/'review-delivery-tests'
        scratch.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            self.assertEqual(Path(folder).resolve().parent,scratch.resolve())
            root=Path(folder)
            for project in [PROJECT]:
                daily=root/project/'daily'; perf=root/project/'performance'
                (daily/'2026-10-30').mkdir(parents=True)
                send=Mock(side_effect=AssertionError('Generation must not send'))
                values=dict(handle_notification_phase=lambda *a:False,send_push=send,
                            json=json,datetime=datetime,MODEL='TEST',
                            read_json=lambda *a:{'review_date':'2026-10-30'},
                            ai_review=lambda *a:{'summary':'test','proposals':[]})
                if project=='CryptoTracker':
                    values.update(args=lambda:SimpleNamespace(date='2026-10-30',no_ai=False),
                                  require_completed_crypto_day=lambda day:None,ANALYSIS_DIR=daily,
                                  build_metrics=lambda raw:{},deterministic_findings=lambda metrics:[],
                                  assign_ids=lambda day,p:p,render_md=lambda *a:'test')
                else:
                    values.update(argparse=argparse,MARKET_TZ=timezone.utc,DAILY_DIR=daily,PERF_DIR=perf,
                                  performance_markdown=lambda *a:'test')
                ns=function_namespace(project,{'main'},**values)
                with patch('sys.argv',['daily_model_review.py','--date','2026-10-30','--defer-notification']):ns['main']()
                send.assert_not_called()
                self.assertTrue((daily/'2026-10-30/daily_model_review.json').is_file())

    @unittest.skipUnless(PROJECT == "CryptoTracker", "Crypto-specific adapter")
    def test_crypto_current_day_never_reaches_model_or_push(self):
        send=Mock();ai=Mock()
        ns=function_namespace('CryptoTracker',{'main'},args=lambda:SimpleNamespace(date='9999-12-31'),
                              require_completed_crypto_day=delivery.require_completed_crypto_day,
                              send_push=send,ai_review=ai)
        with self.assertRaises(ValueError):ns['main']()
        send.assert_not_called();ai.assert_not_called()

    def test_notify_only_does_not_reenter_ai_for_either_project(self):
        for project in [PROJECT]:
            phase=Mock(return_value=True); ai=Mock()
            args=SimpleNamespace(date='2026-10-30')
            values={'handle_notification_phase':phase,'ai_review':ai}
            if project=='CryptoTracker':
                values.update(args=lambda:args,require_completed_crypto_day=lambda day:None)
            else:
                import argparse
                values.update(argparse=argparse,datetime=datetime,MARKET_TZ=timezone.utc)
            ns=function_namespace(project,{'main'},**values)
            with patch('sys.argv',['daily_model_review.py','--date','2026-10-30','--notify-only']):ns['main']()
            ai.assert_not_called();phase.assert_called_once()

    @unittest.skipUnless(PROJECT == "CryptoTracker", "Crypto-specific adapter")
    def test_crypto_sender_validates_json_and_redacts_exceptions(self):
        requests=Mock()
        requests.post.return_value=SimpleNamespace(status_code=200,json=lambda:{'status':0})
        ns=function_namespace('CryptoTracker',{'send_push'},PUSH_ENABLED=True,PUSH_TOKEN='FAKE',PUSH_USER='FAKE',
                              requests=requests,provider_status=delivery.provider_status)
        self.assertEqual(ns['send_push']('2026-10-30',{}),'API_NOT_ACCEPTED')
        requests.post.side_effect=RuntimeError('SECRET')
        self.assertEqual(ns['send_push']('2026-10-30',{}),'UNCONFIRMED')


if __name__=='__main__':unittest.main(verbosity=2)
