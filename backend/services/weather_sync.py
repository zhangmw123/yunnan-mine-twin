"""Open-Meteo 实时气象采集（免 Key）"""
import httpx

from fastapi import APIRouter

from core.config import MINE_CENTER_LAT, MINE_CENTER_LNG

router = APIRouter(prefix="/api/v1/mine", tags=["weather"])

_url = ("https://api.open-meteo.com/v1/forecast"
        f"?latitude={MINE_CENTER_LAT}&longitude={MINE_CENTER_LNG}"
        "&current=temperature_2m,precipitation,rain,weather_code,wind_speed_10m"
        "&hourly=precipitation,temperature_2m&forecast_days=2&timezone=Asia%2FShanghai")


@router.get("/weather")
async def get_weather():
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(_url)
            data = resp.json()
        cur = data["current"]
        return {
            "code": 200,
            "data": {
                "time": cur["time"],
                "temperature_c": cur["temperature_2m"],
                "precipitation_mm": cur["precipitation"],
                "rain_mm": cur["rain"],
                "wind_speed_kmh": cur["wind_speed_10m"],
                "hourly_precipitation": data["hourly"]["precipitation"][:24],
            },
        }
    except Exception as e:
        return {"code": 502, "msg": f"weather api error: {e}", "data": None}
