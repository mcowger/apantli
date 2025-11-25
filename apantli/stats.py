


from fastapi import  Request
from typing import Optional
import datetime
from datetime import datetime, timedelta
from apantli.utils import build_time_filter, build_hour_expr, build_date_expr, convert_local_date_to_utc_range
from apantli.database import RequestFilter

async def stats(request: Request, hours: Optional[int] = None, start_date: Optional[str] = None, end_date: Optional[str] = None, timezone_offset: Optional[int] = None):
    """Get usage statistics, optionally filtered by time range.

    Parameters:
    - hours: Filter to last N hours
    - start_date: ISO 8601 date (YYYY-MM-DD)
    - end_date: ISO 8601 date (YYYY-MM-DD)
    - timezone_offset: Timezone offset in minutes from UTC (e.g., -480 for PST)
    """
    # Build time filter using efficient timestamp comparisons
    time_filter, time_params = build_time_filter(hours, start_date, end_date, timezone_offset)

    # Use Database instance from app state
    db = request.app.state.db
    return await db.get_stats(time_filter=time_filter, time_params=time_params)


async def clear_errors(request: Request):
    """Clear all errors from the database."""
    db = request.app.state.db
    deleted = await db.clear_errors()
    return {"deleted": deleted}


async def stats_daily(request: Request, start_date: Optional[str] = None, end_date: Optional[str] = None, timezone_offset: Optional[int] = None):
    """Get daily aggregated statistics with provider breakdown.

    Parameters:
    - start_date: ISO 8601 date (YYYY-MM-DD), defaults to 30 days ago
    - end_date: ISO 8601 date (YYYY-MM-DD), defaults to today
    - timezone_offset: Timezone offset in minutes from UTC (e.g., -480 for PST)
    """
    # Set default date range if not provided
    if not end_date:
        end_date = datetime.utcnow().strftime('%Y-%m-%d')
    if not start_date:
        # Default to 30 days ago
        start = datetime.utcnow() - timedelta(days=30)
        start_date = start.strftime('%Y-%m-%d')

    # Build WHERE clause using efficient timestamp comparisons
    # and GROUP BY using timezone-adjusted dates
    if timezone_offset is not None:
        # Convert local date range to UTC timestamps for efficient WHERE clause
        start_utc, _ = convert_local_date_to_utc_range(start_date, timezone_offset)
        _, end_utc = convert_local_date_to_utc_range(end_date, timezone_offset)
        where_filter = "timestamp >= ? AND timestamp < ?"
        where_params = [start_utc, end_utc]
    else:
        # No timezone conversion needed
        end_dt = datetime.fromisoformat(end_date) + timedelta(days=1)
        where_filter = "timestamp >= ? AND timestamp < ?"
        where_params = [f"{start_date}T00:00:00", f"{end_dt.date()}T00:00:00"]

    # Build date expression for GROUP BY
    date_expr = build_date_expr(timezone_offset)

    # Use Database instance from app state
    db = request.app.state.db
    return await db.get_daily_stats(start_date, end_date, where_filter, date_expr, where_params)


async def stats_hourly(request: Request, date: str, timezone_offset: Optional[int] = None):
    """Get hourly aggregated statistics for a single day with provider breakdown.

    Parameters:
    - date: ISO 8601 date (YYYY-MM-DD)
    - timezone_offset: Timezone offset in minutes from UTC (e.g., -480 for PST)
    """
    # Build WHERE clause using efficient timestamp comparisons
    # and GROUP BY using timezone-adjusted hours
    if timezone_offset is not None:
        # Convert local date range to UTC timestamps for efficient WHERE clause
        start_utc, end_utc = convert_local_date_to_utc_range(date, timezone_offset)
        where_filter = "timestamp >= ? AND timestamp < ?"
        where_params = [start_utc, end_utc]
    else:
        # No timezone conversion needed
        end_dt = datetime.fromisoformat(date) + timedelta(days=1)
        where_filter = "timestamp >= ? AND timestamp < ?"
        where_params = [f"{date}T00:00:00", f"{end_dt.date()}T00:00:00"]

    # Build hour expression for GROUP BY
    hour_expr = build_hour_expr(timezone_offset)

    # Use Database instance from app state
    db = request.app.state.db
    result = await db.get_hourly_stats(where_filter, hour_expr, where_params)

    # Ensure all 24 hours are present (fill missing hours with zeros)
    hourly_dict = {h['hour']: h for h in result['hourly']}
    hourly_list = []
    for hour in range(24):
        if hour in hourly_dict:
            hourly_list.append(hourly_dict[hour])
        else:
            hourly_list.append({
                'hour': hour,
                'requests': 0,
                'cost': 0.0,
                'total_tokens': 0,
                'by_model': []
            })

    return {
        'hourly': hourly_list,
        'date': date,
        'total_cost': result['total_cost'],
        'total_requests': result['total_requests']
    }

async def stats_date_range(request: Request):
    """Get the actual date range of data in the database."""
    db = request.app.state.db
    return await db.get_date_range()


async def requests(request: Request, hours: Optional[int] = None, start_date: Optional[str] = None, end_date: Optional[str] = None,
                  timezone_offset: Optional[int] = None, offset: int = 0, limit: int = 50,
                  provider: Optional[str] = None, model: Optional[str] = None,
                  min_cost: Optional[float] = None, max_cost: Optional[float] = None, search: Optional[str] = None):
    """Get recent requests with full details, optionally filtered by time range and attributes.

    Parameters:
    - hours: Filter to last N hours
    - start_date: ISO 8601 date (YYYY-MM-DD)
    - end_date: ISO 8601 date (YYYY-MM-DD)
    - timezone_offset: Timezone offset in minutes from UTC (e.g., -480 for PST)
    - offset: Number of records to skip (for pagination)
    - limit: Maximum number of records to return (default: 50, max: 200)
    - provider: Filter by provider name (e.g., 'openai', 'anthropic')
    - model: Filter by model name
    - min_cost: Minimum cost threshold
    - max_cost: Maximum cost threshold
    - search: Search in model name or request/response content
    """
    # Limit the max page size
    limit = min(limit, 200)

    # Build time filter using efficient timestamp comparisons
    time_filter, time_params = build_time_filter(hours, start_date, end_date, timezone_offset)

    # Use Database instance from app state
    db = request.app.state.db
    filters = RequestFilter(
        time_filter=time_filter,
        time_params=time_params,
        offset=offset,
        limit=limit,
        provider=provider,
        model=model,
        min_cost=min_cost,
        max_cost=max_cost,
        search=search
    )
    return await db.get_requests(filters)