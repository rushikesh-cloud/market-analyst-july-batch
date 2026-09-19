"""C03-08/C10-05: opt in with ANALYSIS_LIVE_TESTS=1 and --env-file ../.env."""

import base64
import logging
import os
import time
import unittest

from pydantic import BaseModel

from app.analysis.provider_budget import LocalCallBudget
from app.analysis.provider_runtime import invoke_structured_agent
from app.resources import get_resource_clients
from analysis_capability_image import capability_png


class TextCapability(BaseModel):
    value: int


class VisionCapability(BaseModel):
    label: str
    left_color: str
    left_shape: str
    right_color: str
    right_shape: str


@unittest.skipUnless(os.environ.get('ANALYSIS_LIVE_TESTS') == '1', 'Explicit live-provider opt-in required')
class AzureAnalysisCapabilityTests(unittest.TestCase):
    def setUp(self):
        # SDK diagnostics may include endpoints; this probe reports only safe assertions.
        self.previous_logging_disable = logging.root.manager.disable
        logging.disable(logging.CRITICAL)

    def tearDown(self):
        logging.disable(self.previous_logging_disable)

    def test_c03_08_configured_agents_tool_call_and_structured_output(self):
        resources = get_resource_clients()
        for agent in ('fundamental', 'technical', 'news'):
            with self.subTest(agent=agent):
                calls = []
                def read_probe() -> int:
                    """Read the synthetic capability probe number required for the response."""
                    calls.append(True)
                    return 731
                budget = LocalCallBudget(time.monotonic() + 120)
                output = invoke_structured_agent(
                    model=resources.analysis_chat_model(agent), schema=TextCapability,
                    tools=[read_probe], budget=budget,
                    messages=[{'role':'user', 'content':'Call read_probe exactly once and return its value in the structured response.'}],
                )
                self.assertEqual(output.value, 731)
                self.assertEqual(calls, [True])
                print(f'capability agent={agent} deployment={resources.analysis_model_configuration(agent).deployment} tool=passed schema=passed model_calls={budget.model_calls}')

    def test_c03_08_technical_identifies_actual_labeled_image(self):
        resources = get_resource_clients()
        budget = LocalCallBudget(time.monotonic() + 120)
        image = base64.b64encode(capability_png()).decode('ascii')
        output = invoke_structured_agent(
            model=resources.analysis_chat_model('technical'), schema=VisionCapability,
            budget=budget, image_input=True,
            messages=[{'role':'user','content':[
                {'type':'text','text':'Read the two-character black label exactly, and identify the color and shape on the left and right in the image. Return the structured response.'},
                {'type':'image_url','image_url':{'url':f'data:image/png;base64,{image}'}},
            ]}],
        )
        self.assertEqual(output.label.upper().strip(), 'H7')
        self.assertIn(output.left_color.lower(), ('purple', 'violet'))
        self.assertEqual(output.left_shape.lower(), 'circle')
        self.assertEqual(output.right_color.lower(), 'orange')
        self.assertEqual(output.right_shape.lower(), 'triangle')
        print(f'capability agent=technical deployment={resources.analysis_model_configuration("technical").deployment} vision=passed label=H7 shapes=passed model_calls={budget.model_calls}')
