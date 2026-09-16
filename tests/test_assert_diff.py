import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import assert_diff as ad


def codes(before, after):
    return [f.rule for f in ad.compare_sources(before, after)]


class RuleTests(unittest.TestCase):
    def test_deleted_test(self):
        self.assertEqual(codes('def test_x():\n assert x == 1', ''), ['AD001'])

    def test_deleted_test_uses_old_side(self):
        f = ad.compare_sources('def test_x():\n assert x', '')[0]
        self.assertEqual((f.side, f.line), ('before', 1))

    def test_removed_assertion(self):
        self.assertEqual(codes('def test_x():\n assert x\n assert y', 'def test_x():\n assert x'), ['AD002'])

    def test_duplicate_assertion_removed(self):
        self.assertEqual(codes('def test_x():\n assert x\n assert x', 'def test_x():\n assert x'), ['AD002'])

    def test_changed_expectation(self):
        self.assertEqual(codes('def test_x():\n assert status == 403', 'def test_x():\n assert status == 200'), ['AD003'])

    def test_replaced_same_count(self):
        self.assertEqual(codes('def test_x():\n assert auth\n assert total == 10', 'def test_x():\n assert auth\n assert total'), ['AD003'])

    def test_changed_and_added_assertions(self):
        self.assertEqual(codes('def test_x():\n assert x == 1', 'def test_x():\n assert x == 2\n assert y'), ['AD003'])

    def test_adding_assertion_is_quiet(self):
        self.assertEqual(codes('def test_x():\n assert x', 'def test_x():\n assert x\n assert y'), [])

    def test_format_comments_and_message_quiet(self):
        self.assertEqual(codes('def test_x():\n assert x == 1, "old"', 'def test_x():\n # comment\n assert (x == 1), "new"'), [])

    def test_reordering_assertions_is_quiet(self):
        self.assertEqual(codes('def test_x():\n assert x\n assert y', 'def test_x():\n assert y\n assert x'), [])

    def test_unittest_assertions(self):
        self.assertEqual(codes('class Tests:\n def test_x(self):\n  self.assertEqual(x, 1)', 'class Tests:\n def test_x(self):\n  pass'), ['AD002'])

    def test_raises_changed(self):
        old = 'import pytest\ndef test_x():\n with pytest.raises(ValueError):\n  f()'
        self.assertEqual(codes(old, old.replace('ValueError', 'Exception')), ['AD003'])

    def test_warns_removed(self):
        self.assertEqual(codes('import pytest\ndef test_x():\n with pytest.warns(UserWarning):\n  f()', 'def test_x():\n f()'), ['AD002'])

    def test_alias_import(self):
        self.assertEqual(codes('import pytest as pt\ndef test_x():\n with pt.raises(ValueError):\n  f()', 'def test_x():\n f()'), ['AD002'])

    def test_from_import(self):
        self.assertEqual(codes('from pytest import raises as expecting\ndef test_x():\n with expecting(ValueError):\n  f()', 'def test_x():\n f()'), ['AD002'])

    def test_skip_added(self):
        self.assertEqual(codes('def test_x():\n assert x', 'import pytest\n@pytest.mark.skip(reason="later")\ndef test_x():\n assert x'), ['AD004'])

    def test_xfail_added(self):
        self.assertEqual(codes('', 'import pytest\n@pytest.mark.xfail\ndef test_x():\n assert x'), ['AD004'])

    def test_skip_changed(self):
        old = 'import pytest\n@pytest.mark.skipif(WINDOWS, reason="platform")\ndef test_x():\n assert x'
        self.assertEqual(codes(old, old.replace('WINDOWS', 'True')), ['AD004'])

    def test_unchanged_skip_quiet(self):
        code = 'import pytest\n@pytest.mark.skip\ndef test_x():\n assert x'
        self.assertEqual(codes(code, code), [])

    def test_skip_removed_quiet(self):
        self.assertEqual(codes('import pytest\n@pytest.mark.skip\ndef test_x():\n assert x', 'def test_x():\n assert x'), [])

    def test_runtime_skip(self):
        self.assertEqual(codes('def test_x():\n assert x', 'import pytest\ndef test_x():\n pytest.skip("later")\n assert x'), ['AD004'])

    def test_unittest_skip(self):
        self.assertEqual(codes('', 'import unittest\n@unittest.skip("later")\nclass Tests:\n def test_x(self):\n  self.assertTrue(x)'), ['AD004'])

    def test_class_skip(self):
        self.assertEqual(codes('', 'import pytest\n@pytest.mark.skip\nclass TestSuite:\n def test_x(self):\n  assert x\n def test_y(self):\n  assert y'), ['AD004', 'AD004'])

    def test_module_skip_single_finding(self):
        self.assertEqual(codes('', 'import pytest\npytestmark = pytest.mark.skip(reason="later")\ndef test_x():\n assert x'), ['AD004'])

    def test_module_skip_list(self):
        self.assertEqual(codes('', 'import pytest\npytestmark = [pytest.mark.slow, pytest.mark.xfail]\ndef test_x():\n assert x'), ['AD004'])

    def test_parameter_cases_reduced(self):
        old = 'import pytest\n@pytest.mark.parametrize("x", [1, 2, 3])\ndef test_x(x):\n assert f(x)'
        self.assertEqual(codes(old, old.replace('[1, 2, 3]', '[1]')), ['AD005'])

    def test_parameter_keywords(self):
        old = 'import pytest\n@pytest.mark.parametrize(argnames="x", argvalues=(1, 2))\ndef test_x(x):\n assert f(x)'
        self.assertEqual(codes(old, old.replace('(1, 2)', '(1,)')), ['AD005'])

    def test_parameter_removed(self):
        old = 'import pytest\n@pytest.mark.parametrize("x", [1, 2])\ndef test_x(x):\n assert f(x)'
        self.assertEqual(codes(old, 'def test_x(x):\n assert f(x)'), ['AD005'])

    def test_parameter_became_dynamic(self):
        old = 'import pytest\n@pytest.mark.parametrize("x", [1, 2])\ndef test_x(x):\n assert f(x)'
        self.assertEqual(codes(old, old.replace('[1, 2]', 'CASES')), ['AD005'])

    def test_added_parameter_cases_quiet(self):
        old = 'import pytest\n@pytest.mark.parametrize("x", [1, 2])\ndef test_x(x):\n assert f(x)'
        self.assertEqual(codes(old, old.replace('[1, 2]', '[1, 2, 3]')), [])

    def test_constant_true(self):
        self.assertEqual(codes('', 'def test_x():\n assert True'), ['AD006'])

    def test_literal_equality(self):
        self.assertEqual(codes('', 'def test_x():\n assert 1 == 1'), ['AD006'])

    def test_constant_false_is_not_trivial_pass(self):
        self.assertEqual(codes('', 'def test_x():\n assert False'), [])

    def test_overloaded_equality_is_not_guessed(self):
        self.assertEqual(codes('', 'def test_x():\n assert x == x'), [])

    def test_existing_trivial_is_quiet(self):
        code = 'def test_x():\n assert True'
        self.assertEqual(codes(code, code), [])

    def test_async_test(self):
        self.assertEqual(codes('async def test_x():\n assert x', 'async def test_x():\n pass'), ['AD002'])

    def test_local_helper_not_counted(self):
        self.assertEqual(codes('def test_x():\n def helper():\n  assert x\n helper()', 'def test_x():\n helper()'), [])

    def test_non_test_helper_ignored(self):
        self.assertEqual(codes('def helper():\n assert x', ''), [])

    def test_class_names_do_not_collide(self):
        old = 'class A:\n def test_x(self):\n  assert x\nclass B:\n def test_x(self):\n  assert y'
        findings = ad.compare_sources(old, old.replace('assert y', 'pass'))
        self.assertEqual([f.test for f in findings], ['B.test_x'])

    def test_syntax_error_not_clean(self):
        data = ad.report({'test_a.py': 'def broken('}, {}, 'base', 'head')
        self.assertEqual(len(data['errors']), 1)

    def test_no_source_execution(self):
        data = ad.report({}, {'test_a.py': 'raise RuntimeError("must not execute")\ndef test_x():\n assert True'}, 'base', 'head')
        self.assertEqual(data['summary']['findings'], 1)


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.before, self.after = self.root / 'before', self.root / 'after'
        self.before.mkdir()
        self.after.mkdir()
        (self.before / 'test_sample.py').write_text('def test_x():\n assert x', encoding='utf-8')
        (self.after / 'test_sample.py').write_text('def test_x():\n pass', encoding='utf-8')

    def cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            status = ad.main(list(map(str, args)))
        return status, output.getvalue()

    def test_advisory_exit(self):
        code, text = self.cli('compare', self.before, self.after)
        self.assertEqual(code, 0)
        self.assertIn('AD002', text)

    def test_strict_exit(self):
        code, _ = self.cli('compare', self.before, self.after, '--fail-on', 'findings')
        self.assertEqual(code, 1)

    def test_json_report(self):
        code, text = self.cli('compare', self.before, self.after, '--format', 'json')
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(text)['summary']['findings'], 1)

    def test_invalid_directory(self):
        code, text = self.cli('compare', self.root / 'missing', self.after, '--format', 'json')
        self.assertEqual(code, 2)
        self.assertIn('error', json.loads(text))

    def test_parse_error_exit(self):
        (self.after / 'test_sample.py').write_text('def invalid(', encoding='utf-8')
        code, text = self.cli('compare', self.before, self.after, '--format', 'json')
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(text)['summary']['errors'], 1)

    def test_source_encoding(self):
        (self.after / 'test_latin.py').write_bytes(b'# coding: latin-1\ndef test_caf\xe9():\n assert True\n')
        code, text = self.cli('compare', self.before, self.after, '--format', 'json')
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(text)['summary']['tests_after'], 2)

    def test_include_custom_filename(self):
        (self.before / 'checks.py').write_text('def test_y():\n assert y')
        self.assertEqual(len(ad.directory_sources(self.before, [])), 1)
        self.assertEqual(list(ad.directory_sources(self.before, ['checks.py'])), ['checks.py'])

    def test_ignored_directories(self):
        (self.after / 'node_modules').mkdir()
        (self.after / 'node_modules' / 'test_bad.py').write_text('not python!')
        self.assertEqual(len(ad.directory_sources(self.after, [])), 1)

    def test_symlink_source_rejected(self):
        path = self.after / 'test_link.py'
        try:
            path.symlink_to(self.before / 'test_sample.py')
        except OSError:
            self.skipTest('Symlink creation is unavailable for this OS/user')
        with self.assertRaisesRegex(ValueError, 'symbolic-link'):
            ad.directory_sources(self.after, [])

    def test_oversize_source(self):
        (self.after / 'test_big.py').write_bytes(b' ' * (ad.MAX_FILE_BYTES + 1))
        with self.assertRaisesRegex(ValueError, '2 MiB'):
            ad.directory_sources(self.after, [])

    def test_annotation_escaping(self):
        self.assertEqual(ad.annotation('x%,:\n', True), 'x%25%2C%3A%0A')

    def test_terminal_escaping(self):
        self.assertNotIn('\x1b', ad.safe('\x1b[31mevil'))

    def test_markdown_escaping(self):
        text = ad.markdown('<script>|`hello`')
        self.assertNotIn('<script>', text)
        self.assertNotIn('|', text)

    def test_deleted_annotation_has_no_head_line(self):
        data = ad.report({'test_x.py': 'def test_x():\n assert x'}, {}, 'base', 'head')
        self.assertIn('::warning title=Removed test::', ad.render(data, 'github'))

    def test_git_revisions(self):
        repo = self.root / 'git-repo'
        repo.mkdir()

        def git(*args):
            result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, check=True)
            return result.stdout.decode().strip()

        git('init', '-b', 'main')
        git('config', 'user.name', 'Test Fixture')
        git('config', 'user.email', 'fixture@example.invalid')
        git('config', 'commit.gpgsign', 'false')
        source = repo / 'test space.py'
        source.write_text('def test_x():\n assert x', encoding='utf-8')
        git('add', '.')
        git('commit', '-m', 'before')
        base = git('rev-parse', 'HEAD')
        source.write_text('def test_x():\n pass', encoding='utf-8')
        git('add', '.')
        git('commit', '-m', 'after')
        head = git('rev-parse', 'HEAD')
        code, text = self.cli('git', '--repo', repo, '--base', base, '--head', head, '--include', '*.py', '--format', 'json', '--fail-on', 'findings')
        data = json.loads(text)
        self.assertEqual(code, 1)
        self.assertEqual(data['baseline'], base)
        self.assertEqual(data['candidate'], head)
        self.assertEqual(data['findings'][0]['rule'], 'AD002')
        self.assertEqual(git('status', '--porcelain'), '')

    def test_git_invalid_revision(self):
        code, _ = self.cli('git', '--repo', self.root, '--base=--help')
        self.assertEqual(code, 2)


if __name__ == '__main__':
    unittest.main()
