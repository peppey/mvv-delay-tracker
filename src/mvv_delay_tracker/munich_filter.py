import math


def wgs84_to_utm32(latitude, longitude):
    """
    Convert WGS84 coordinates to UTM Zone 32N.
    """

    earth_semi_major_axis = 6378137.0
    eccentricity_squared = 0.00669437999014
    scale_factor = 0.9996

    latitude_radians = math.radians(latitude)
    longitude_radians = math.radians(longitude)

    central_meridian_radians = math.radians(9.0)

    second_eccentricity_squared = (
        eccentricity_squared
        / (1 - eccentricity_squared)
    )

    radius_of_curvature = (
        earth_semi_major_axis
        / math.sqrt(
            1
            - eccentricity_squared
            * math.sin(latitude_radians) ** 2
        )
    )

    tangent_squared = math.tan(latitude_radians) ** 2

    cosine_term = (
        second_eccentricity_squared
        * math.cos(latitude_radians) ** 2
    )

    longitude_difference = (
        math.cos(latitude_radians)
        * (
            longitude_radians
            - central_meridian_radians
        )
    )

    meridional_arc = earth_semi_major_axis * (
        (
            1
            - eccentricity_squared / 4
            - 3 * eccentricity_squared**2 / 64
            - 5 * eccentricity_squared**3 / 256
        )
        * latitude_radians

        - (
            3 * eccentricity_squared / 8
            + 3 * eccentricity_squared**2 / 32
            + 45 * eccentricity_squared**3 / 1024
        )
        * math.sin(2 * latitude_radians)

        + (
            15 * eccentricity_squared**2 / 256
            + 45 * eccentricity_squared**3 / 1024
        )
        * math.sin(4 * latitude_radians)

        - (
            35 * eccentricity_squared**3 / 3072
        )
        * math.sin(6 * latitude_radians)
    )

    easting = (
        scale_factor
        * radius_of_curvature
        * (
            longitude_difference
            + (
                1
                - tangent_squared
                + cosine_term
            )
            * longitude_difference**3
            / 6
            + (
                5
                - 18 * tangent_squared
                + tangent_squared**2
                + 72 * cosine_term
                - 58 * second_eccentricity_squared
            )
            * longitude_difference**5
            / 120
        )
        + 500000.0
    )

    northing = scale_factor * (
        meridional_arc
        + radius_of_curvature
        * math.tan(latitude_radians)
        * (
            longitude_difference**2 / 2

            + (
                5
                - tangent_squared
                + 9 * cosine_term
                + 4 * cosine_term**2
            )
            * longitude_difference**4
            / 24

            + (
                61
                - 58 * tangent_squared
                + tangent_squared**2
                + 600 * cosine_term
                - 330 * second_eccentricity_squared
            )
            * longitude_difference**6
            / 720
        )
    )

    return easting, northing


def point_is_inside_polygon(
    point_x,
    point_y,
    polygon_coordinates
):
    """
    Determine whether a point lies inside a polygon.
    """

    point_is_inside = False

    number_of_vertices = len(
        polygon_coordinates
    )

    for vertex_index in range(
        number_of_vertices
    ):

        current_vertex_x, current_vertex_y = (
            polygon_coordinates[vertex_index]
        )

        next_vertex_x, next_vertex_y = (
            polygon_coordinates[
                (vertex_index + 1) % number_of_vertices
            ]
        )

        if (
            current_vertex_y > point_y
        ) != (
            next_vertex_y > point_y
        ):

            x_intersection = (
                (next_vertex_x - current_vertex_x)
                * (point_y - current_vertex_y)
                / (next_vertex_y - current_vertex_y)
                + current_vertex_x
            )

            if point_x < x_intersection:
                point_is_inside = not point_is_inside

    return point_is_inside


def point_is_inside_munich(
    point_x,
    point_y,
    munich_geojson
):
    """
    Determine whether a point lies within Munich.
    """

    for geojson_feature in munich_geojson["features"]:

        geometry = geojson_feature["geometry"]
        geometry_type = geometry["type"]

        if geometry_type == "Polygon":

            polygon_rings = geometry["coordinates"]

            for polygon_ring in polygon_rings:

                if point_is_inside_polygon(
                    point_x,
                    point_y,
                    polygon_ring
                ):
                    return True

        elif geometry_type == "MultiPolygon":

            polygons = geometry["coordinates"]

            for polygon in polygons:

                polygon_rings = polygon

                for polygon_ring in polygon_rings:

                    if point_is_inside_polygon(
                        point_x,
                        point_y,
                        polygon_ring
                    ):
                        return True

    return False