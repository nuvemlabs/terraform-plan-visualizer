"""Structural validation tests for extract.sh JSON output."""

import json
import os
import subprocess
import unittest

EXTRACT_SH = os.path.join(os.path.dirname(__file__), '..', 'extract.sh')
FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')

REQUIRED_TOP_LEVEL = ('metadata', 'summary', 'resources', 'warnings', 'refreshCount')
REQUIRED_SUMMARY = ('create', 'update', 'destroy', 'replace', 'move', 'read', 'import', 'total')
REQUIRED_METADATA = ('generated', 'source', 'terraform_version')
REQUIRED_RESOURCE = ('address', 'module', 'type', 'name', 'action', 'forcesReplacement', 'changes', 'diffBlock')


def run_extract(fixture_name):
    fixture = os.path.join(FIXTURES, fixture_name)
    result = subprocess.run(
        [EXTRACT_SH, fixture],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)


class TestTopLevelStructure(unittest.TestCase):
    """Verify top-level JSON structure across multiple fixtures."""

    FIXTURE_LIST = [
        'no_changes.log', 'single_create.log', 'single_update.log',
        'single_destroy.log', 'mixed_actions.log', 'zero_count_bug.log',
    ]

    def test_all_fixtures_have_required_keys(self):
        for fixture in self.FIXTURE_LIST:
            with self.subTest(fixture=fixture):
                data = run_extract(fixture)
                self.assertIsNotNone(data, f"{fixture}: failed to parse JSON")
                for key in REQUIRED_TOP_LEVEL:
                    self.assertIn(key, data, f"{fixture}: missing top-level key '{key}'")


class TestMetadataSchema(unittest.TestCase):

    def test_metadata_has_required_fields(self):
        data = run_extract('single_create.log')
        for key in REQUIRED_METADATA:
            self.assertIn(key, data['metadata'], f"Missing metadata key '{key}'")

    def test_metadata_source_is_filename(self):
        data = run_extract('single_create.log')
        self.assertEqual(data['metadata']['source'], 'single_create.log')

    def test_generated_is_iso_format(self):
        data = run_extract('single_create.log')
        generated = data['metadata']['generated']
        self.assertRegex(generated, r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')


class TestSummarySchema(unittest.TestCase):

    def test_summary_has_all_action_types(self):
        data = run_extract('mixed_actions.log')
        for key in REQUIRED_SUMMARY:
            self.assertIn(key, data['summary'], f"Missing summary key '{key}'")

    def test_summary_values_are_integers(self):
        data = run_extract('mixed_actions.log')
        for key in REQUIRED_SUMMARY:
            self.assertIsInstance(
                data['summary'][key], int,
                f"summary.{key} should be int, got {type(data['summary'][key])}"
            )

    def test_summary_values_non_negative(self):
        data = run_extract('mixed_actions.log')
        for key in REQUIRED_SUMMARY:
            self.assertGreaterEqual(
                data['summary'][key], 0,
                f"summary.{key} should be >= 0"
            )


class TestResourceSchema(unittest.TestCase):

    def test_resources_is_list(self):
        data = run_extract('mixed_actions.log')
        self.assertIsInstance(data['resources'], list)

    def test_each_resource_has_required_fields(self):
        data = run_extract('mixed_actions.log')
        for i, r in enumerate(data['resources']):
            with self.subTest(resource=i, address=r.get('address', 'unknown')):
                for key in REQUIRED_RESOURCE:
                    self.assertIn(key, r, f"Resource {i} missing '{key}'")

    def test_action_is_valid_type(self):
        valid_actions = {'create', 'update', 'destroy', 'replace', 'move', 'read', 'import', 'unknown'}
        data = run_extract('mixed_actions.log')
        for r in data['resources']:
            self.assertIn(r['action'], valid_actions, f"Invalid action: {r['action']}")

    def test_changes_is_list(self):
        data = run_extract('mixed_actions.log')
        for r in data['resources']:
            self.assertIsInstance(r['changes'], list)

    def test_forces_replacement_is_bool(self):
        data = run_extract('mixed_actions.log')
        for r in data['resources']:
            self.assertIsInstance(r['forcesReplacement'], bool)


class TestWarningsSchema(unittest.TestCase):

    def test_warnings_is_list(self):
        data = run_extract('warnings_present.log')
        self.assertIsInstance(data['warnings'], list)

    def test_each_warning_has_title_and_message(self):
        data = run_extract('warnings_present.log')
        for i, w in enumerate(data['warnings']):
            with self.subTest(warning=i):
                self.assertIn('title', w)
                self.assertIn('message', w)
                self.assertIsInstance(w['title'], str)
                self.assertIsInstance(w['message'], str)


class TestRefreshCountSchema(unittest.TestCase):

    def test_refresh_count_is_integer(self):
        data = run_extract('no_changes.log')
        self.assertIsInstance(data['refreshCount'], int)

    def test_refresh_count_non_negative(self):
        data = run_extract('single_create.log')
        self.assertGreaterEqual(data['refreshCount'], 0)


if __name__ == '__main__':
    unittest.main()
