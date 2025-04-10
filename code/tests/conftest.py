import pytest
import json

@pytest.fixture
def form_recognizer_response_v2():
	json_path = "fixtures/CSVN515208_form_recognizer_response_v2.json"
	with open(json_path, "rb") as f:
		json_data = json.load(f)
	return json_data


@pytest.fixture
def form_recognizer_response_v3():
	json_path = "fixtures/CSVN515208_form_recognizer_response_v3.json"
	with open(json_path, "rb") as f:
		json_data = json.load(f)
	return json_data