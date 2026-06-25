"""Tests for the AIECO emissions methodology and the server-side calculators."""
import json
from unittest.mock import patch

from django.test import TestCase, Client
from django.core.cache import cache

from . import methodology as method
from .models import HardwareSpec, OperationType, PrecisionType, CarbonRegion
from . import views


class MethodologyTests(TestCase):
    """The pure estimation pipeline — no database, deterministic."""

    def test_estimate_emissions_structure_and_token_split(self):
        r = method.estimate_emissions(
            word_count=100, wh_per_token=0.0000030, carbon_intensity_kg_kwh=0.207,
        )
        # 100 words -> round(100 * 1.33) = 133 input tokens; output ratio 1.0.
        self.assertEqual(r['input_tokens'], 133)
        self.assertEqual(r['output_tokens'], 133)
        self.assertEqual(r['total_tokens'], 266)
        self.assertEqual(r['pue'], method.DEFAULT_PUE)
        self.assertGreater(r['energy_wh'], 0)

    def test_uncertainty_bounds_bracket_the_central_value(self):
        low, high = method.uncertainty_bounds(100.0)
        self.assertLess(low, 100.0)
        self.assertGreater(high, 100.0)

    def test_uncertainty_lower_bound_is_floored_at_zero(self):
        low, high = method.uncertainty_bounds(0.0)
        self.assertEqual(low, 0.0)
        self.assertEqual(high, 0.0)

    def test_combined_uncertainty_is_quadrature_sum(self):
        import math
        expected = math.sqrt(sum(u * u for u in method.UNCERTAINTY_COMPONENTS.values()))
        self.assertAlmostEqual(method.combined_relative_uncertainty(), expected)


class HwCalculateTests(TestCase):
    """The server-side hardware calculator endpoint."""

    def setUp(self):
        self.client = Client()
        self.hw = HardwareSpec.objects.create(
            name='Test GPU', manufacturer='Test', tdp_watts=500.0)
        self.op = OperationType.objects.create(
            name='Inference', slug='inference', energy_mult=1.0)
        self.prec = PrecisionType.objects.create(
            name='FP32', slug='fp32', energy_factor=1.0)
        self.region = CarbonRegion.objects.create(
            region_name='Testland', region_code='TST', carbon_intensity_kg_kwh=0.5)

    def _post(self, **overrides):
        payload = {
            'hardware_id': self.hw.id, 'operation_id': self.op.id,
            'precision_id': self.prec.id, 'region_id': self.region.id,
            'gpus': 8, 'hours': 24,
        }
        payload.update(overrides)
        return self.client.post('/api/hw-calculate/', data=json.dumps(payload),
                                content_type='application/json')

    def test_valid_request_matches_formula(self):
        resp = self._post()
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # (TDP x GPUs x op_mult x prec_factor x PUE x hours) / 1000
        expected = (500.0 * 8 * 1.0 * 1.0 * views.HW_PUE * 24) / 1000.0
        self.assertAlmostEqual(data['energy_kwh'], expected)
        self.assertAlmostEqual(data['co2_kg'], expected * 0.5)

    def test_gpu_count_is_clamped(self):
        # 9999 GPUs should be clamped to the UI maximum of 512.
        resp = self._post(gpus=9999)
        expected = (500.0 * 512 * 1.0 * 1.0 * views.HW_PUE * 24) / 1000.0
        self.assertAlmostEqual(resp.json()['energy_kwh'], expected)

    def test_unknown_selection_returns_400(self):
        resp = self._post(hardware_id=999999)
        self.assertEqual(resp.status_code, 400)

    def test_malformed_body_returns_400(self):
        resp = self.client.post('/api/hw-calculate/', data='not json',
                                content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get('/api/hw-calculate/').status_code, 405)


class ChatApiAbuseTests(TestCase):
    """Rate limiting and input caps on the public Gemini proxy."""

    def setUp(self):
        self.client = Client()
        cache.clear()  # rate-limit counters live in the cache

    @patch.dict('os.environ', {'GEMINI_API_KEY': ''})
    def test_rate_limit_blocks_after_threshold(self):
        # Requests up to the limit succeed (unconfigured -> friendly 200 reply).
        for _ in range(views.CHAT_RATE_LIMIT):
            ok = self.client.post('/api/chat/', data=json.dumps({'message': 'hi'}),
                                  content_type='application/json')
            self.assertEqual(ok.status_code, 200)
        # The next one trips the limit.
        blocked = self.client.post('/api/chat/', data=json.dumps({'message': 'hi'}),
                                   content_type='application/json')
        self.assertEqual(blocked.status_code, 429)

    @patch.dict('os.environ', {'GEMINI_API_KEY': ''})
    def test_overlong_message_rejected(self):
        resp = self.client.post(
            '/api/chat/',
            data=json.dumps({'message': 'x' * (views.CHAT_MAX_MESSAGE_LEN + 1)}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 400)
