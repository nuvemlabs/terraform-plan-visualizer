"""Unit tests for extract.sh — the terraform plan parser."""

import json
import os
import subprocess
import unittest

EXTRACT_SH = os.path.join(os.path.dirname(__file__), '..', 'extract.sh')
FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')


def run_extract(fixture_name):
    """Run extract.sh on a fixture, return (returncode, parsed_json_or_None, raw_stdout, stderr)."""
    fixture = os.path.join(FIXTURES, fixture_name)
    result = subprocess.run(
        [EXTRACT_SH, fixture],
        capture_output=True, text=True, timeout=30
    )
    data = None
    if result.returncode == 0 and result.stdout.strip():
        data = json.loads(result.stdout)
    return result.returncode, data, result.stdout, result.stderr


def find_resource(data, address_substring):
    """Find a resource by partial address match."""
    for r in data['resources']:
        if address_substring in r['address']:
            return r
    return None


def find_change(resource, attribute):
    """Find a change by attribute name."""
    for c in resource.get('changes', []):
        if c['attribute'] == attribute:
            return c
    return None


class TestNoChanges(unittest.TestCase):
    """Test plan with no actions — only refreshing state."""

    @classmethod
    def setUpClass(cls):
        cls.rc, cls.data, cls.raw, cls.err = run_extract('no_changes.log')

    def test_exit_code_zero(self):
        self.assertEqual(self.rc, 0)

    def test_valid_json(self):
        self.assertIsNotNone(self.data)

    def test_summary_all_zeros(self):
        s = self.data['summary']
        for key in ('create', 'update', 'destroy', 'replace', 'move', 'read', 'import', 'total'):
            self.assertEqual(s[key], 0, f"Expected {key}=0, got {s[key]}")

    def test_resources_empty(self):
        self.assertEqual(self.data['resources'], [])

    def test_refresh_count_is_integer(self):
        self.assertIsInstance(self.data['refreshCount'], int)

    def test_refresh_count_positive(self):
        self.assertGreaterEqual(self.data['refreshCount'], 1)

    def test_metadata_source(self):
        self.assertEqual(self.data['metadata']['source'], 'no_changes.log')

    def test_metadata_generated_present(self):
        self.assertIn('generated', self.data['metadata'])
        self.assertTrue(len(self.data['metadata']['generated']) > 0)


class TestSingleCreate(unittest.TestCase):
    """Test plan with one resource creation."""

    @classmethod
    def setUpClass(cls):
        cls.rc, cls.data, cls.raw, cls.err = run_extract('single_create.log')

    def test_valid_json(self):
        self.assertIsNotNone(self.data)

    def test_summary_create_one(self):
        self.assertEqual(self.data['summary']['create'], 1)

    def test_summary_others_zero(self):
        s = self.data['summary']
        for key in ('update', 'destroy', 'replace', 'move', 'read', 'import'):
            self.assertEqual(s[key], 0, f"Expected {key}=0")

    def test_resource_count(self):
        self.assertEqual(len(self.data['resources']), 1)

    def test_resource_action(self):
        self.assertEqual(self.data['resources'][0]['action'], 'create')

    def test_resource_type(self):
        self.assertEqual(self.data['resources'][0]['type'], 'azurerm_resource_group')

    def test_resource_name_contains_example(self):
        self.assertIn('example', self.data['resources'][0]['name'])

    def test_resource_module_is_root(self):
        self.assertEqual(self.data['resources'][0]['module'], 'root')

    def test_changes_include_name(self):
        r = self.data['resources'][0]
        c = find_change(r, 'name')
        self.assertIsNotNone(c, "Expected change for attribute 'name'")
        self.assertEqual(c['action'], 'add')

    def test_changes_include_location(self):
        r = self.data['resources'][0]
        c = find_change(r, 'location')
        self.assertIsNotNone(c)
        self.assertEqual(c['action'], 'add')

    def test_diff_block_present(self):
        self.assertTrue(len(self.data['resources'][0]['diffBlock']) > 0)

    def test_forces_replacement_false(self):
        self.assertFalse(self.data['resources'][0]['forcesReplacement'])

    def test_total_equals_resource_count(self):
        self.assertEqual(self.data['summary']['total'], len(self.data['resources']))


class TestSingleUpdate(unittest.TestCase):
    """Test plan with one resource update."""

    @classmethod
    def setUpClass(cls):
        cls.rc, cls.data, cls.raw, cls.err = run_extract('single_update.log')

    def test_valid_json(self):
        self.assertIsNotNone(self.data)

    def test_summary_update_one(self):
        self.assertEqual(self.data['summary']['update'], 1)

    def test_resource_action(self):
        self.assertEqual(self.data['resources'][0]['action'], 'update')

    def test_change_has_old_and_new(self):
        r = self.data['resources'][0]
        c = find_change(r, 'enable_https_traffic_only')
        self.assertIsNotNone(c)
        self.assertEqual(c['action'], 'change')
        self.assertTrue(len(c['old']) > 0)
        self.assertTrue(len(c['new']) > 0)

    def test_diff_block_contains_tilde(self):
        self.assertIn('~', self.data['resources'][0]['diffBlock'])

    def test_total_equals_resource_count(self):
        self.assertEqual(self.data['summary']['total'], len(self.data['resources']))


class TestSingleDestroy(unittest.TestCase):
    """Test plan with one resource destruction."""

    @classmethod
    def setUpClass(cls):
        cls.rc, cls.data, cls.raw, cls.err = run_extract('single_destroy.log')

    def test_valid_json(self):
        self.assertIsNotNone(self.data)

    def test_summary_destroy_one(self):
        self.assertEqual(self.data['summary']['destroy'], 1)

    def test_resource_action(self):
        self.assertEqual(self.data['resources'][0]['action'], 'destroy')

    def test_destroy_changes_have_name(self):
        r = self.data['resources'][0]
        c = find_change(r, 'name')
        self.assertIsNotNone(c, "Expected 'name' in destroy changes")
        self.assertEqual(c['action'], 'remove')

    def test_destroy_changes_have_description(self):
        r = self.data['resources'][0]
        c = find_change(r, 'description')
        self.assertIsNotNone(c, "Expected 'description' in destroy changes")

    def test_keyed_resource_has_key(self):
        r = self.data['resources'][0]
        self.assertIn('key', r)
        self.assertIn('HighCPU', r['key'])

    def test_total_equals_resource_count(self):
        self.assertEqual(self.data['summary']['total'], len(self.data['resources']))


class TestSingleReplace(unittest.TestCase):
    """Test plan with one resource replacement."""

    @classmethod
    def setUpClass(cls):
        cls.rc, cls.data, cls.raw, cls.err = run_extract('single_replace.log')

    def test_valid_json(self):
        self.assertIsNotNone(self.data)

    def test_summary_replace_one(self):
        self.assertEqual(self.data['summary']['replace'], 1)

    def test_resource_action(self):
        self.assertEqual(self.data['resources'][0]['action'], 'replace')

    def test_forces_replacement_true(self):
        self.assertTrue(self.data['resources'][0]['forcesReplacement'])

    def test_change_with_forces_annotation(self):
        r = self.data['resources'][0]
        forces_changes = [c for c in r['changes'] if c.get('forcesReplacement')]
        self.assertGreater(len(forces_changes), 0, "Expected at least one change with forcesReplacement")

    def test_total_equals_resource_count(self):
        self.assertEqual(self.data['summary']['total'], len(self.data['resources']))


class TestSingleMove(unittest.TestCase):
    """Test plan with one resource move."""

    @classmethod
    def setUpClass(cls):
        cls.rc, cls.data, cls.raw, cls.err = run_extract('single_move.log')

    def test_valid_json(self):
        self.assertIsNotNone(self.data)

    def test_summary_move_one(self):
        self.assertEqual(self.data['summary']['move'], 1)

    def test_resource_action(self):
        self.assertEqual(self.data['resources'][0]['action'], 'move')

    def test_move_from_populated(self):
        r = self.data['resources'][0]
        self.assertIn('moveFrom', r)
        self.assertTrue(len(r['moveFrom']) > 0)
        self.assertIn('old_module', r['moveFrom'])

    def test_address_is_new_location(self):
        r = self.data['resources'][0]
        self.assertIn('servicebus_rbac', r['address'])

    def test_total_equals_resource_count(self):
        self.assertEqual(self.data['summary']['total'], len(self.data['resources']))


class TestSingleImport(unittest.TestCase):
    """Test plan with one imported resource."""

    @classmethod
    def setUpClass(cls):
        cls.rc, cls.data, cls.raw, cls.err = run_extract('single_import.log')

    def test_valid_json(self):
        self.assertIsNotNone(self.data)

    def test_resource_action_is_import(self):
        self.assertEqual(self.data['resources'][0]['action'], 'import')

    def test_import_id_populated(self):
        r = self.data['resources'][0]
        self.assertIn('importId', r)
        self.assertIn('Microsoft.ServiceBus', r['importId'])

    def test_total_equals_resource_count(self):
        self.assertEqual(self.data['summary']['total'], len(self.data['resources']))


class TestSingleRead(unittest.TestCase):
    """Test plan with a data source read during apply."""

    @classmethod
    def setUpClass(cls):
        cls.rc, cls.data, cls.raw, cls.err = run_extract('single_read.log')

    def test_valid_json(self):
        self.assertIsNotNone(self.data)

    def test_summary_read_one(self):
        self.assertEqual(self.data['summary']['read'], 1)

    def test_read_resource_exists(self):
        r = find_resource(self.data, 'client_config')
        self.assertIsNotNone(r)
        self.assertEqual(r['action'], 'read')

    def test_also_has_create_resource(self):
        r = find_resource(self.data, 'azurerm_resource_group')
        self.assertIsNotNone(r)
        self.assertEqual(r['action'], 'create')

    def test_total_equals_resource_count(self):
        self.assertEqual(self.data['summary']['total'], len(self.data['resources']))


class TestMixedActions(unittest.TestCase):
    """Test plan with create + update + destroy together."""

    @classmethod
    def setUpClass(cls):
        cls.rc, cls.data, cls.raw, cls.err = run_extract('mixed_actions.log')

    def test_valid_json(self):
        self.assertIsNotNone(self.data)

    def test_summary_create(self):
        self.assertEqual(self.data['summary']['create'], 2)

    def test_summary_update(self):
        self.assertEqual(self.data['summary']['update'], 1)

    def test_summary_destroy(self):
        self.assertEqual(self.data['summary']['destroy'], 1)

    def test_resource_count(self):
        self.assertEqual(len(self.data['resources']), 4)

    def test_total_equals_resource_count(self):
        self.assertEqual(self.data['summary']['total'], len(self.data['resources']))

    def test_each_resource_has_correct_action(self):
        actions = sorted([r['action'] for r in self.data['resources']])
        self.assertEqual(actions, ['create', 'create', 'destroy', 'update'])


class TestModuleResources(unittest.TestCase):
    """Test parsing of resources inside modules."""

    @classmethod
    def setUpClass(cls):
        cls.rc, cls.data, cls.raw, cls.err = run_extract('module_resources.log')

    def test_valid_json(self):
        self.assertIsNotNone(self.data)

    def test_servicebus_module_parsed(self):
        r = find_resource(self.data, 'servicebus')
        self.assertIsNotNone(r)
        self.assertEqual(r['module'], 'module.servicebus')

    def test_naming_module_parsed(self):
        r = find_resource(self.data, 'naming')
        self.assertIsNotNone(r)
        self.assertEqual(r['module'], 'module.naming')

    def test_type_extracted(self):
        r = find_resource(self.data, 'servicebus')
        self.assertEqual(r['type'], 'azurerm_servicebus_topic')


class TestModuleNested(unittest.TestCase):
    """Test parsing of deeply nested module paths."""

    @classmethod
    def setUpClass(cls):
        cls.rc, cls.data, cls.raw, cls.err = run_extract('module_nested.log')

    def test_valid_json(self):
        self.assertIsNotNone(self.data)

    def test_nested_module_path(self):
        r = self.data['resources'][0]
        self.assertIn('module.platform', r['module'])
        self.assertIn('module.servicebus', r['module'])

    def test_type_is_namespace(self):
        self.assertEqual(self.data['resources'][0]['type'], 'azurerm_servicebus_namespace')


class TestKeyedResources(unittest.TestCase):
    """Test resources with for_each and count keys."""

    @classmethod
    def setUpClass(cls):
        cls.rc, cls.data, cls.raw, cls.err = run_extract('keyed_resources.log')

    def test_valid_json(self):
        self.assertIsNotNone(self.data)

    def test_string_key_populated(self):
        r = find_resource(self.data, 'alerts')
        self.assertIsNotNone(r)
        self.assertIn('key', r)
        self.assertIn('HighCPU', r['key'])

    def test_numeric_key_resource(self):
        r = find_resource(self.data, 'function_app')
        self.assertIsNotNone(r, "Expected to find function_app resource")


class TestHeredocContent(unittest.TestCase):
    """Test that heredoc blocks don't break resource parsing."""

    @classmethod
    def setUpClass(cls):
        cls.rc, cls.data, cls.raw, cls.err = run_extract('heredoc_content.log')

    def test_valid_json(self):
        self.assertIsNotNone(self.data)

    def test_single_resource_parsed(self):
        self.assertEqual(len(self.data['resources']), 1)

    def test_diff_block_contains_heredoc(self):
        r = self.data['resources'][0]
        self.assertIn('EOT', r['diffBlock'])

    def test_diff_block_contains_xml(self):
        r = self.data['resources'][0]
        self.assertIn('policies', r['diffBlock'])


class TestWarnings(unittest.TestCase):
    """Test warning extraction from plan output."""

    @classmethod
    def setUpClass(cls):
        cls.rc, cls.data, cls.raw, cls.err = run_extract('warnings_present.log')

    def test_valid_json(self):
        self.assertIsNotNone(self.data)

    def test_warnings_count(self):
        self.assertEqual(len(self.data['warnings']), 2)

    def test_first_warning_title(self):
        self.assertIn('undeclared variable', self.data['warnings'][0]['title'])

    def test_second_warning_title(self):
        self.assertIn('deprecated', self.data['warnings'][1]['title'])

    def test_warnings_have_messages(self):
        for w in self.data['warnings']:
            self.assertTrue(len(w['message']) > 0, "Warning message should not be empty")


class TestAnsiCodes(unittest.TestCase):
    """Test that ANSI escape codes are stripped from output."""

    @classmethod
    def setUpClass(cls):
        cls.rc, cls.data, cls.raw, cls.err = run_extract('ansi_codes.log')

    def test_valid_json(self):
        self.assertIsNotNone(self.data)

    def test_no_ansi_in_output(self):
        self.assertNotIn('\x1b', self.raw)

    def test_correct_update_count(self):
        self.assertEqual(self.data['summary']['update'], 1)

    def test_resource_parsed(self):
        self.assertEqual(len(self.data['resources']), 1)
        self.assertEqual(self.data['resources'][0]['action'], 'update')


class TestSpecialChars(unittest.TestCase):
    """Test handling of quotes, backslashes, and tabs in values."""

    @classmethod
    def setUpClass(cls):
        cls.rc, cls.data, cls.raw, cls.err = run_extract('special_chars.log')

    def test_valid_json(self):
        self.assertIsNotNone(self.data)

    def test_diff_block_present(self):
        r = self.data['resources'][0]
        self.assertTrue(len(r['diffBlock']) > 0)


class TestZeroCountRegression(unittest.TestCase):
    """Regression test for grep -c double output bug.

    When grep -c finds 0 matches, it outputs '0' AND exits code 1.
    The old pattern `$(grep -c ... || echo "0")` captured both outputs: "0\\n0".
    This produced invalid JSON in the summary section.

    The fixture has creates + update + destroy but ZERO moves, reads, or replaces.
    """

    @classmethod
    def setUpClass(cls):
        cls.rc, cls.data, cls.raw, cls.err = run_extract('zero_count_bug.log')

    def test_valid_json(self):
        self.assertIsNotNone(self.data, "JSON parsing failed — regression bug may be present")

    def test_move_is_integer_zero(self):
        self.assertIsInstance(self.data['summary']['move'], int)
        self.assertEqual(self.data['summary']['move'], 0)

    def test_read_is_integer_zero(self):
        self.assertIsInstance(self.data['summary']['read'], int)
        self.assertEqual(self.data['summary']['read'], 0)

    def test_replace_is_integer_zero(self):
        self.assertIsInstance(self.data['summary']['replace'], int)
        self.assertEqual(self.data['summary']['replace'], 0)

    def test_refresh_count_is_integer(self):
        self.assertIsInstance(self.data['refreshCount'], int)

    def test_no_newline_in_raw_summary(self):
        """Ensure no '0\\n0' pattern in the raw JSON output."""
        # Find the summary section in raw output
        summary_start = self.raw.find('"summary"')
        summary_end = self.raw.find('}', self.raw.find('}', summary_start) + 1)
        summary_section = self.raw[summary_start:summary_end]
        self.assertNotIn('0\n0', summary_section, "Double-zero bug detected in summary")

    def test_total_is_correct_integer(self):
        self.assertIsInstance(self.data['summary']['total'], int)
        self.assertEqual(self.data['summary']['total'], len(self.data['resources']))

    def test_total_equals_resource_count(self):
        """Total should equal the number of resources in the array."""
        self.assertEqual(self.data['summary']['total'], 3)


class TestTotalConsistency(unittest.TestCase):
    """Verify summary.total matches len(resources) across all fixtures."""

    def _check_fixture(self, fixture_name):
        rc, data, raw, err = run_extract(fixture_name)
        self.assertEqual(rc, 0, f"{fixture_name}: non-zero exit code")
        self.assertIsNotNone(data, f"{fixture_name}: invalid JSON")
        self.assertEqual(
            data['summary']['total'],
            len(data['resources']),
            f"{fixture_name}: total ({data['summary']['total']}) != resources ({len(data['resources'])})"
        )

    def test_no_changes(self):
        self._check_fixture('no_changes.log')

    def test_single_create(self):
        self._check_fixture('single_create.log')

    def test_single_update(self):
        self._check_fixture('single_update.log')

    def test_single_destroy(self):
        self._check_fixture('single_destroy.log')

    def test_single_replace(self):
        self._check_fixture('single_replace.log')

    def test_single_move(self):
        self._check_fixture('single_move.log')

    def test_mixed_actions(self):
        self._check_fixture('mixed_actions.log')

    def test_zero_count_bug(self):
        self._check_fixture('zero_count_bug.log')


if __name__ == '__main__':
    unittest.main()
