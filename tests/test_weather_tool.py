import pytest
from pydantic import ValidationError

from backend.tools.weather import WeatherTool


class FakeWeatherProvider:
    def __init__(self, response):
        self.response = response

    def get_weather_forecast(self, destination, date="", day=1):
        return self.response


def valid_weather():
    return {
        "destination": "Goa",
        "day": 2,
        "condition": "heavy_rain_warning",
        "temperature_c": 26.5,
        "suitableForOutdoor": False,
        "evidence": "Heavy rain expected on day 2.",
    }


def test_valid_weather_response_is_accepted():
    tool = WeatherTool()
    provider = FakeWeatherProvider(valid_weather())

    result = tool.execute(provider, destination="Goa", day=2)

    assert result["destination"] == "Goa"
    assert result["day"] == 2
    assert result["suitableForOutdoor"] is False


def test_missing_weather_suitability_is_rejected():
    response = valid_weather()
    del response["suitableForOutdoor"]

    tool = WeatherTool()
    provider = FakeWeatherProvider(response)

    with pytest.raises(ValidationError):
        tool.execute(provider, destination="Goa", day=2)


def test_invalid_weather_suitability_type_is_rejected():
    response = valid_weather()
    response["suitableForOutdoor"] = "unknown"

    tool = WeatherTool()
    provider = FakeWeatherProvider(response)

    with pytest.raises(ValidationError):
        tool.execute(provider, destination="Goa", day=2)


def test_weather_for_wrong_day_is_rejected():
    response = valid_weather()
    response["day"] = 3

    tool = WeatherTool()
    provider = FakeWeatherProvider(response)

    with pytest.raises(ValueError, match="different itinerary day"):
        tool.execute(provider, destination="Goa", day=2)


def test_weather_for_wrong_destination_is_rejected():
    response = valid_weather()
    response["destination"] = "Mumbai"

    tool = WeatherTool()
    provider = FakeWeatherProvider(response)

    with pytest.raises(ValueError, match="different destination"):
        tool.execute(provider, destination="Goa", day=2)