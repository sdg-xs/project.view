"""Exact planar convex hulls and deterministic minimum-area rectangles."""

from __future__ import annotations

import math
from dataclasses import dataclass

Point2 = tuple[float, float]


def convex_hull(points: list[Point2]) -> list[Point2]:
    ordered = sorted(set(points))
    if len(ordered) <= 2:
        return ordered

    def half(vertices):
        result = []
        for point in vertices:
            while len(result) >= 2:
                a, b = result[-2:]
                if (b[0] - a[0]) * (point[1] - a[1]) > (b[1] - a[1]) * (point[0] - a[0]):
                    break
                result.pop()
            result.append(point)
        return result

    return half(ordered)[:-1] + half(reversed(ordered))[:-1]


@dataclass(frozen=True)
class Rectangle:
    cosine: float
    sine: float
    minimum: Point2
    maximum: Point2


def minimum_rectangle(hull: list[Point2]) -> Rectangle:
    """Fit a nonempty counterclockwise hull in linear hull time."""
    if len(hull) == 1:
        return Rectangle(1.0, 0.0, hull[0], hull[0])

    count = len(hull)
    supports = None
    best_area = math.inf
    best_angle = 0.0
    for i, point in enumerate(hull):
        following = hull[(i + 1) % count]
        dx, dy = following[0] - point[0], following[1] - point[1]
        length = math.hypot(dx, dy)
        cosine, sine = dx / length, dy / length
        directions = ((cosine, sine), (-sine, cosine), (-cosine, -sine), (sine, -cosine))
        if supports is None:
            supports = [max(range(count), key=lambda j: hull[j][0] * x + hull[j][1] * y) for x, y in directions]
        values = []
        for side, (x, y) in enumerate(directions):
            index = supports[side]
            while True:
                following_index = (index + 1) % count
                current = hull[index][0] * x + hull[index][1] * y
                following_value = hull[following_index][0] * x + hull[following_index][1] * y
                if following_value <= current:
                    break
                index = following_index
            supports[side] = index
            values.append(hull[index][0] * x + hull[index][1] * y)
        area = max(0.0, values[0] + values[2]) * max(0.0, values[1] + values[3])
        angle = math.atan2(sine, cosine) % (math.pi / 2)
        area_scale = max(area, best_area if math.isfinite(best_area) else 0.0)
        tolerance = max(1e-10 * area_scale, 8 * math.ulp(area_scale))
        if area < best_area - tolerance or (abs(area - best_area) <= tolerance and angle < best_angle):
            best_area, best_angle = area, angle

    cosine, sine = math.cos(best_angle), math.sin(best_angle)
    horizontal = [x * cosine + y * sine for x, y in hull]
    vertical = [-x * sine + y * cosine for x, y in hull]
    return Rectangle(cosine, sine, (min(horizontal), min(vertical)), (max(horizontal), max(vertical)))
