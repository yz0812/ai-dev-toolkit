import json
import subprocess
import sys
import unittest
from pathlib import Path


class ExportOpenapiFromJavaRegressionTest(unittest.TestCase):
    def test_photovoltaic_statistics_preserves_field_descriptions_and_number_types(self):
        test_dir = Path(__file__).resolve().parent
        fixture = test_dir / "fixtures" / "tmp_photovoltaic_business_center.java"
        script = test_dir.parent / "scripts" / "export_openapi_from_java.py"

        completed = subprocess.run(
            [
                sys.executable,
                str(script),
                "--source",
                str(fixture),
                "--method",
                "photovoltaicStatistics",
                "--metadata-only",
            ],
            cwd=str(script.parent),
            capture_output=True,
            text=True,
            check=True,
        )

        payload = json.loads(completed.stdout)
        response_schema = payload["responseSchema"]
        properties = response_schema["properties"]

        self.assertEqual(properties["powerGeneration"]["description"], "发电量")
        self.assertEqual(properties["onGridEnergy"]["description"], "上网电量")
        self.assertEqual(properties["onGridEnergyYoy"]["description"], "同比上网电量")

        numeric_fields = [
            "powerGeneration",
            "powerGenerationYoy",
            "powerGenerationMom",
            "powerGenerationYoyRate",
            "powerGenerationMomRate",
            "onGridEnergy",
            "onGridEnergyYoy",
            "onGridEnergyMom",
            "onGridEnergyYoyRate",
            "onGridEnergyMomRate",
        ]
        for field_name in numeric_fields:
            self.assertEqual(properties[field_name]["type"], "number", field_name)
            self.assertEqual(payload["responseExample"][field_name], 0.0, field_name)

        self.assertEqual(payload["schemaWarnings"], [])


if __name__ == "__main__":
    unittest.main()
