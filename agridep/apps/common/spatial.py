import math
from typing import Tuple, Optional
from django.db.models import F, FloatField, ExpressionWrapper
from django.db.models.functions import Sin, Cos, ACos, Radians

def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Computes great-circle distance between two points on Earth in kilometres
    using the Haversine formula.
    """
    R = 6371.0  # Earth's radius in kilometers
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    
    a = (math.sin(d_lat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(d_lon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def annotate_distance_km(queryset, target_lat: float, target_lon: float, lat_field: str = 'latitude', lon_field: str = 'longitude'):
    """
    Annotates a Django QuerySet with `distance_km` from a target coordinate
    using standard SQL trigonometric functions.
    Works seamlessly on PostgreSQL, SQLite, and MySQL without requiring external C extensions.
    """
    # 6371 * acos(cos(radians(target_lat)) * cos(radians(lat)) * cos(radians(lon) - radians(target_lon)) + sin(radians(target_lat)) * sin(radians(lat)))
    rad_lat1 = math.radians(target_lat)
    rad_lon1 = math.radians(target_lon)
    
    expr = ExpressionWrapper(
        6371.0 * ACos(
            Cos(rad_lat1) * Cos(Radians(F(lat_field))) *
            Cos(Radians(F(lon_field)) - rad_lon1) +
            Sin(rad_lat1) * Sin(Radians(F(lat_field)))
        ),
        output_field=FloatField()
    )
    return queryset.annotate(distance_km=expr)
