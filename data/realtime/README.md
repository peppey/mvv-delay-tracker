# MVV Realtime Data

This directory contains the collected MVV/GTFS-Realtime observations stored in
`mvv_realtime.parquet`. Each row represents one observed stop visit for a trip
at a particular observation time.

## Columns

| Column | Description |
| --- | --- |
| `observation_timestamp` | Local date and time at which the GTFS-Realtime feed was collected. Stored as a timezone-naive timestamp representing `Europe/Berlin` time. |
| `trip_id` | Identifier of the scheduled trip from the static GTFS data. |
| `start_date` | Service date of the trip in `YYYYMMDD` format. |
| `trip_schedule_relationship` | Relationship between the realtime trip and the scheduled trip, for example `SCHEDULED`, `ADDED`, `CANCELED`, or `DUPLICATED`. |
| `stop_schedule_relationship` | Relationship between the observed stop visit and the scheduled stop visit, for example `SCHEDULED`, `SKIPPED`, or `NO_DATA`. |
| `line` | Public-facing line name, such as `S6`, `U3`, or `18`. |
| `agency_id` | Identifier of the transport operator in the static GTFS `agency.txt` data. |
| `agency_name` | Human-readable name of the transport operator, from the static GTFS `agency.txt` data. |
| `stop_id` | Identifier of the stop in the static GTFS data. |
| `stop_name` | Human-readable name of the observed stop. |
| `stop_sequence` | Position of the stop within the trip. It identifies the stop visit together with `trip_id`. |
| `departure_time` | Observed or predicted departure date and time at the stop. Stored as a timezone-naive timestamp representing `Europe/Berlin` time. |
| `departure_delay` | Departure delay in seconds. Positive values indicate a delay; negative values indicate an early departure. |
| `arrival_time` | Observed or predicted arrival date and time at the stop. Stored as a timezone-naive timestamp representing `Europe/Berlin` time. |
| `arrival_delay` | Arrival delay in seconds. Positive values indicate a delay; negative values indicate an early arrival. |
| `is_prediction` | `True` if the stop visit had not yet been observed after its scheduled arrival at collection time (a live prediction). `False` once the arrival has been confirmed, or if the stop visit was `SKIPPED`. |

## Notes

- `departure_time`, `arrival_time`, and `observation_timestamp` are stored as
  local German time (`Europe/Berlin`) without timezone metadata in the Parquet
  file.
- `departure_delay` and `arrival_delay` are measured in seconds, not minutes.
- Missing arrival or departure values are expected for observations where the
  corresponding information was not provided by the realtime feed.
- A unique stop visit is identified by `trip_id`, `start_date`, and `stop_id`.
- When a stop visit is observed again after a prediction, the confirmed
  observation (`is_prediction == False`) replaces the earlier prediction for
  the same `trip_id`, `start_date`, and `stop_id`.
