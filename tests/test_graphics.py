import unittest

from native_port import graphics
from native_port.errors import PortError


class GraphicsPresetTests(unittest.TestCase):
    def test_presets_map_to_expected_rendering_values(self):
        expected = {
            'low': (1, True, 1, 'low', False),
            'default': (1, True, 3, 'default', False),
            'high': (1, True, 4, 'high', False),
            'ultra': (1, True, 5, 'ultra', False),
        }
        for name, values in expected.items():
            with self.subTest(preset=name):
                data = graphics.from_options(name, fps_target='30', vsync=True)
                actual = (data['render_scale'], data['msaa_2x'], data['anisotropic'],
                          data['texture_quality'], data['present_dither'])
                self.assertEqual(actual, values)
                self.assertEqual(data['preset'], name)

    def test_explicit_override_switches_to_custom_and_keeps_value(self):
        data = graphics.from_options('ultra', render_scale=1, msaa_2x=False,
                                     anisotropic=1, texture_quality='low',
                                     present_dither=True, fps_target='60', vsync=True)
        self.assertEqual(data['preset'], 'custom')
        self.assertEqual(data['render_scale'], 1)
        self.assertFalse(data['msaa_2x'])
        self.assertTrue(data['present_dither'])
        self.assertEqual(data['fps_target'], '60')

    def test_custom_preset_preserves_current_values(self):
        current = graphics.from_options('high', fps_target='60', vsync=True)
        data = graphics.apply_preset('custom', current)
        self.assertEqual(data['preset'], 'custom')
        self.assertEqual(data['render_scale'], current['render_scale'])
        self.assertEqual(data['texture_quality'], current['texture_quality'])

    def test_internal_resolution_and_texture_limits(self):
        self.assertEqual(graphics.internal_resolution(1), '1280x720')
        self.assertEqual(graphics.internal_resolution(3), '3840x2160')
        self.assertEqual(graphics.texture_limits('ultra'), (768, 1536, 48))

    def test_full_hd_output_is_independent_of_internal_scale(self):
        data = graphics.from_options('default', output_resolution='1920x1080')
        self.assertEqual(data['render_scale'], 1)
        self.assertEqual(data['output_resolution'], '1920x1080')
        self.assertIn('--window_width=1920', graphics.cvar_arguments(data))
        self.assertIn('--window_height=1080', graphics.cvar_arguments(data))
        self.assertEqual(graphics.apply_preset('high', data)['output_resolution'], '1920x1080')
        with self.assertRaises(PortError):
            graphics.from_options(output_resolution='1920x1080 --bad')

    def test_cvar_arguments_are_deterministic_real_flags(self):
        data = graphics.from_options('high', fps_target='30', vsync=True)
        arguments = graphics.cvar_arguments(data)
        self.assertEqual(arguments, [
            '--resolution_scale=1', '--anisotropic_override=4',
            '--texture_cache_memory_limit_soft=512',
            '--texture_cache_memory_limit_hard=1024',
            '--texture_cache_memory_limit_render_to_texture=32',
            '--present_dither=false'])

    def test_unlimited_always_disables_vsync_without_touching_other_fields(self):
        data = graphics.from_options('low', fps_target='unlimited', vsync=True)
        self.assertFalse(data['vsync'])
        self.assertEqual(data['render_scale'], 1)
        self.assertEqual(data['fps_target'], 'unlimited')

    def test_invalid_values_are_rejected(self):
        for field, value in [('preset', 'cinema'), ('render_scale', 0), ('render_scale', 4),
                             ('render_scale', True), ('anisotropic', -2), ('anisotropic', 6),
                             ('fps_target', '120'), ('texture_quality', 'ultra2'),
                             ('shader_mode', 'instant'), ('vsync', 'off')]:
            with self.subTest(field=field), self.assertRaises(PortError):
                data = graphics.from_options('custom', fps_target='30', vsync=True)
                data[field] = value
                graphics.validate(data)


if __name__ == '__main__':
    unittest.main()
