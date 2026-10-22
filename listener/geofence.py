"""Cerca fixa da chegada em casa, em (longitude, latitude)."""

from shapely.geometry import Point, Polygon


AREA_VERTICES: tuple[tuple[float, float], ...] = (
    (-35.2073938, -5.8312213),
    (-35.2075107, -5.831536),
    (-35.2073933, -5.8315756),
    (-35.207277, -5.8312686),
    (-35.2073938, -5.8312213),
)

HOME_AREA = Polygon(AREA_VERTICES)


def contains_home(longitude: float, latitude: float) -> bool:
    return bool(HOME_AREA.contains(Point(longitude, latitude)))
