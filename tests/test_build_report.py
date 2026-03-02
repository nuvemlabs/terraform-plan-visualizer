"""Integration tests for build-report.sh — the full pipeline."""

import json
import os
import subprocess
import tempfile
import unittest

BUILD_REPORT_SH = os.path.join(os.path.dirname(__file__), '..', 'build-report.sh')
FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')


class TestBuildReport(unittest.TestCase):
    """Test the full pipeline: plan.log -> JSON -> HTML report."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.output_file = os.path.join(self.tmpdir, 'report.html')

    def tearDown(self):
        if os.path.exists(self.output_file):
            os.unlink(self.output_file)
        os.rmdir(self.tmpdir)

    def run_build(self, fixture_name, output=None):
        fixture = os.path.join(FIXTURES, fixture_name)
        cmd = [BUILD_REPORT_SH, fixture]
        if output:
            cmd.append(output)
        else:
            cmd.append(self.output_file)
        # Set TERM to avoid any terminal-related issues
        env = os.environ.copy()
        env['TERM'] = 'dumb'
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, env=env
        )

    def test_generates_html_file(self):
        result = self.run_build('single_create.log')
        self.assertEqual(result.returncode, 0, f"build-report.sh failed: {result.stderr}")
        self.assertTrue(os.path.exists(self.output_file))

    def test_html_contains_plan_data(self):
        self.run_build('single_create.log')
        with open(self.output_file) as f:
            html = f.read()
        self.assertIn('const PLAN_DATA =', html)

    def test_html_valid_structure(self):
        self.run_build('single_create.log')
        with open(self.output_file) as f:
            html = f.read()
        self.assertIn('<!DOCTYPE html>', html)
        self.assertIn('</html>', html)

    def test_json_embedded_in_html(self):
        """Extract and parse the JSON from the HTML to verify it's valid."""
        self.run_build('mixed_actions.log')
        with open(self.output_file) as f:
            html = f.read()
        # Extract JSON between 'const PLAN_DATA = ' and ';\n</script>'
        start_marker = 'const PLAN_DATA = '
        end_marker = ';\n</script>'
        start = html.find(start_marker) + len(start_marker)
        end = html.find(end_marker, start)
        json_str = html[start:end]
        data = json.loads(json_str)
        self.assertIn('summary', data)
        self.assertIn('resources', data)

    def test_custom_output_path(self):
        custom_path = os.path.join(self.tmpdir, 'custom-report.html')
        result = self.run_build('single_create.log', output=custom_path)
        self.assertEqual(result.returncode, 0)
        self.assertTrue(os.path.exists(custom_path))
        os.unlink(custom_path)

    def test_missing_file_error(self):
        result = subprocess.run(
            [BUILD_REPORT_SH, '/nonexistent/file.log', self.output_file],
            capture_output=True, text=True, timeout=10
        )
        self.assertNotEqual(result.returncode, 0)

    def test_stdout_shows_progress(self):
        result = self.run_build('single_create.log')
        combined = result.stdout + result.stderr
        self.assertIn('Extracting', combined)
        self.assertIn('Report generated', combined)


if __name__ == '__main__':
    unittest.main()
