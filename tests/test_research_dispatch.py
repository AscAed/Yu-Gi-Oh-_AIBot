import contextlib
import io
import sys
import unittest
from unittest.mock import patch

from ygo_eval.research import main


class ResearchDispatch(unittest.TestCase):
    def invoke(self, outcome):
        argv = ['research', 'native-regression']
        for name in ('cases', 'runner', 'worker', 'build-record', 'identity', 'old-ledger', 'window-start', 'output'):
            argv += ['--' + name, 'synthetic']
        with patch.object(sys, 'argv', argv), patch(
            'ygo_eval.native_regression.native_regression', **outcome
        ), contextlib.redirect_stdout(io.StringIO()) as output:
            code = main()
        return code, output.getvalue()

    def test_native_dispatch_returns_exit_code_and_json(self):
        code, output = self.invoke({'return_value': {'successful': True}})
        self.assertEqual(code, 0)
        self.assertIn('"successful": true', output)
        self.assertEqual(self.invoke({'return_value': {'successful': False}})[0], 1)
        self.assertEqual(self.invoke({'return_value': {'prepared': True}})[0], 0)

    def test_invalid_input_diagnostic_does_not_echo_private_path(self):
        code, output = self.invoke({'side_effect': ValueError('private/local/path')})
        self.assertEqual(code, 2)
        self.assertNotIn('private', output)

    def test_history_audit_dispatch_preserves_saved_failure_exit(self):
        argv=['research','audit-history','--baseline-dir','synthetic','--output','synthetic']
        for valid,expected in [(True,0),(False,1)]:
            with patch.object(sys,'argv',argv),patch('ygo_eval.history_audit.audit_to_output',return_value={'valid':valid,'native_calls':0}) as auditor,patch('ygo_eval.terminal_followup.subprocess.run') as runner,contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(),expected)
                auditor.assert_called_once();runner.assert_not_called()
                self.assertIn('"native_calls": 0',output.getvalue())

    def test_history_audit_dispatch_refusal_sanitizes_private_paths(self):
        argv=['research','audit-history','--baseline-dir','synthetic','--output','synthetic']
        with patch.object(sys,'argv',argv),patch('ygo_eval.history_audit.audit_to_output',side_effect=ValueError('private/local/path')),contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(),2)
            self.assertNotIn('private',output.getvalue())

    def test_confirmation_runner_audit_dispatch_keeps_zero_call_scope(self):
        argv = [
            'research', 'audit-tenki-confirmation-runner',
            '--baseline-dir', 'baseline', '--runner', 'runner',
            '--build-record', 'build', '--output', 'report',
        ]
        for status, expected in (('passed', 0), ('failed', 1), ('incomplete', 1)):
            with patch.object(sys, 'argv', argv), patch(
                'ygo_eval.tenki_confirmation_runner_audit.run_audit',
                return_value={'status': status, 'diagnostic': None},
            ) as audit, contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(), expected)
                audit.assert_called_once()
                self.assertIn('"native_calls": 0', output.getvalue())
                self.assertIn('"execution_ready": false', output.getvalue())

    def test_confirmation_runner_audit_dispatch_sanitizes_exceptions(self):
        argv = [
            'research', 'audit-tenki-confirmation-runner',
            '--baseline-dir', 'baseline', '--runner', 'runner',
            '--build-record', 'build', '--output', 'report',
        ]
        with patch.object(sys, 'argv', argv), patch(
            'ygo_eval.tenki_confirmation_runner_audit.run_audit',
            side_effect=ValueError('D:\\private\\material'),
        ), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(), 2)
            self.assertNotIn('private', output.getvalue())

    def test_curry_asset_binding_audit_dispatch_keeps_zero_call_scope(self):
        argv = [
            'research', 'audit-curry-asset-binding',
            '--baseline-dir', 'baseline', '--runner', 'runner',
            '--build-record', 'build', '--output', 'output',
        ]
        for status, expected in (('passed', 0), ('failed', 1), ('incomplete', 1)):
            with patch.object(sys, 'argv', argv), patch(
                'ygo_eval.curry_asset_binding_audit.run_audit',
                return_value={
                    'status': status,
                    'native_calls': 0,
                    'execution_ready': False,
                },
            ) as audit, contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(), expected)
                audit.assert_called_once()
                self.assertIn('"native_calls": 0', output.getvalue())
                self.assertIn('"execution_ready": false', output.getvalue())

    def test_curry_asset_binding_audit_dispatch_sanitizes_exceptions(self):
        argv = [
            'research', 'audit-curry-asset-binding',
            '--baseline-dir', 'baseline', '--runner', 'runner',
            '--build-record', 'build', '--output', 'output',
        ]
        with patch.object(sys, 'argv', argv), patch(
            'ygo_eval.curry_asset_binding_audit.run_audit',
            side_effect=ValueError('D:\\private\\material'),
        ), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(), 2)
            self.assertNotIn('private', output.getvalue())

    def test_curry_option_verification_dispatch_is_registered_and_sanitized(self):
        argv = ['research', 'native-curry-option-verification']
        for name in ('baseline-dir', 'preparation', 'cases', 'core-source', 'runner',
                     'worker', 'build-record', 'identity', 'window-start', 'output'):
            argv += ['--' + name, 'synthetic']
        for report, expected in (({'prepared': True}, 0), ({'successful': False}, 1)):
            with patch.object(sys, 'argv', argv), patch(
                'ygo_eval.native_curry_option_validation.native_curry_option_verification',
                return_value=report,
            ) as workflow, contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(), expected)
                workflow.assert_called_once()
                self.assertIn('"prepared": true' if 'prepared' in report else '"successful": false',
                              output.getvalue())

        with patch.object(sys, 'argv', argv), patch(
            'ygo_eval.native_curry_option_validation.native_curry_option_verification',
            side_effect=ValueError('D:\\private\\artifact'),
        ), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(), 2)
            self.assertNotIn('private', output.getvalue())

    def test_curry_input_recovery_dispatch_forwards_report_version_and_keeps_zero_calls(self):
        argv = [
            'research', 'audit-curry-input-recovery', '--report-version', '2',
            '--baseline-dir', 'baseline', '--output', 'output',
        ]
        for status, expected in (('passed', 0), ('failed', 1), ('incomplete', 1)):
            with patch.object(sys, 'argv', argv), patch(
                'ygo_eval.curry_input_recovery_audit.audit_to_output',
                return_value={
                    'status': status, 'schema_version': 2, 'native_calls': 0,
                    'execution_ready': False,
                },
            ) as audit, contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(), expected)
                audit.assert_called_once()
                self.assertEqual(audit.call_args.args[0].report_version, 2)
                self.assertIn('"native_calls": 0', output.getvalue())
                self.assertIn('"execution_ready": false', output.getvalue())

        with patch.object(sys, 'argv', argv), patch(
            'ygo_eval.curry_input_recovery_audit.audit_to_output',
            side_effect=ValueError('D:\\private\\historical-material'),
        ), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(), 2)
            self.assertNotIn('private', output.getvalue())

    def test_tenki_validation_dispatch_exposes_fixed_modes_and_sanitizes_errors(self):
        argv = [
            'research', 'native-tenki-placement-validation',
            '--baseline-dir', 'baseline', '--runner', 'runner', '--worker', 'worker',
            '--build-record', 'build', '--identity', 'identity',
            '--window-start', 'window', '--output', 'output', '--prepare-only',
        ]
        for result, expected in (({'prepared': True}, 0), ({'successful': True}, 0),
                                 ({'successful': False}, 1)):
            with patch.object(sys, 'argv', argv), patch(
                'ygo_eval.native_tenki_placement_validation.native_tenki_placement_validation',
                return_value=result,
            ) as run, contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(), expected)
                run.assert_called_once()
                if 'prepared' in result:
                    self.assertIn('"prepared": true', output.getvalue())
        with patch.object(sys, 'argv', argv), patch(
            'ygo_eval.native_tenki_placement_validation.native_tenki_placement_validation',
            side_effect=ValueError('D:\\private\\frozen-input'),
        ), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(), 2)
            self.assertNotIn('private', output.getvalue())

    def test_tenki_validation_verify_only_uses_valid_result_for_exit_status(self):
        argv = [
            'research', 'native-tenki-placement-validation',
            '--baseline-dir', 'baseline', '--runner', 'runner', '--worker', 'worker',
            '--build-record', 'build', '--identity', 'identity',
            '--window-start', 'window', '--output', 'output', '--verify-only',
        ]
        for result, expected in (({'valid': True, 'native_calls': 0}, 0),
                                 ({'valid': False, 'native_calls': 0}, 1)):
            with patch.object(sys, 'argv', argv), patch(
                'ygo_eval.native_tenki_placement_validation.native_tenki_placement_validation',
                return_value=result,
            ), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(), expected)
                self.assertIn('"native_calls": 0', output.getvalue())

    def test_curry_validation_dispatch_has_separate_scope_and_modes(self):
        argv = [
            'research', 'native-curry-option-validation',
            '--baseline-dir', 'baseline', '--preparation', 'preparation',
            '--cases', 'cases', '--core-source', 'operations.cpp',
            '--runner', 'runner', '--worker', 'worker', '--build-record', 'build',
            '--identity', 'identity', '--window-start', 'window', '--output', 'output',
            '--prepare-only',
        ]
        for result, expected in (({'prepared': True}, 0),
                                 ({'successful': True}, 0),
                                 ({'successful': False}, 1),
                                 ({'valid': True, 'native_calls': 0}, 0)):
            with patch.object(sys, 'argv', argv), patch(
                'ygo_eval.native_curry_option_validation.native_curry_option_validation',
                return_value=result,
            ) as run, contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(), expected)
                run.assert_called_once()
                if "native_calls" in result:
                    self.assertIn('"native_calls": 0', output.getvalue())

    def test_curry_validation_dispatch_sanitizes_failures(self):
        argv = [
            'research', 'native-curry-option-validation',
            '--baseline-dir', 'baseline', '--preparation', 'preparation',
            '--cases', 'cases', '--core-source', 'operations.cpp',
            '--runner', 'runner', '--worker', 'worker', '--build-record', 'build',
            '--identity', 'identity', '--window-start', 'window', '--output', 'output',
            '--verify-only',
        ]
        with patch.object(sys, 'argv', argv), patch(
            'ygo_eval.native_curry_option_validation.native_curry_option_validation',
            side_effect=ValueError('D:\\private\\history'),
        ), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(), 2)
            self.assertNotIn('private', output.getvalue())

    def test_curry_confirmation_dispatch_is_fixed_and_sanitizes_failures(self):
        argv = [
            'research', 'native-curry-option-confirmation',
            '--baseline-dir', 'baseline', '--preparation', 'preparation',
            '--cases', 'cases', '--core-source', 'operations.cpp',
            '--runner', 'runner', '--worker', 'worker', '--build-record', 'build',
            '--identity', 'identity', '--window-start', 'window', '--output', 'output',
            '--verify-only',
        ]
        for result, expected in (({'prepared': True}, 0),
                                 ({'successful': True}, 0),
                                 ({'valid': True, 'native_calls': 0}, 0),
                                 ({'successful': False}, 1)):
            with patch.object(sys, 'argv', argv), patch(
                'ygo_eval.native_curry_option_validation.native_curry_option_confirmation',
                return_value=result,
            ) as run, contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(), expected)
                run.assert_called_once()
                self.assertNotIn('D:\\', output.getvalue())

        with patch.object(sys, 'argv', argv), patch(
            'ygo_eval.native_curry_option_validation.native_curry_option_confirmation',
            side_effect=ValueError('D:\\private\\history'),
        ), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(), 2)
            self.assertNotIn('private', output.getvalue())

        with patch.object(sys, 'argv', argv + ['--limit', '6']):
            with self.assertRaises(SystemExit):
                main()
