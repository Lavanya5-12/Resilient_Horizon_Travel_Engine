from backend.providers.demo import DemoProvider


def test_goa_day_2_has_heavy_rain_warning():
    provider = DemoProvider()

    result = provider.get_weather_forecast("Goa", day=2)

    assert result["day"] == 2
    assert result["condition"] == "heavy_rain_warning"
    assert result["suitableForOutdoor"] is False


def test_goa_day_3_is_sunny_even_when_date_says_day_2():
    provider = DemoProvider()

    result = provider.get_weather_forecast("Goa", date="Day 2", day=3)

    assert result["day"] == 3
    assert result["condition"] == "sunny"
    assert result["suitableForOutdoor"] is True


def test_goa_day_3_with_flexible_date_is_sunny():
    provider = DemoProvider()

    result = provider.get_weather_forecast("Goa", date="Flexible", day=3)

    assert result["day"] == 3
    assert result["condition"] == "sunny"
    assert result["suitableForOutdoor"] is True
