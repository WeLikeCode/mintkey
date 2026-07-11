package budget

import "time"

// PeriodBounds returns the UTC-aligned (start, end) for the given period
// containing the reference time t.
//
// Period alignment (design §3):
//   - hourly:  top of the hour → +1 hour
//   - daily:   00:00:00Z → +24 hours
//   - weekly:  Monday 00:00:00Z → +7 days
//   - monthly: 1st of month 00:00:00Z → 1st of next month 00:00:00Z
//
// Unknown period values default to daily.
func PeriodBounds(period string, t time.Time) (start, end time.Time) {
	t = t.UTC()

	switch period {
	case "hourly":
		start = time.Date(t.Year(), t.Month(), t.Day(), t.Hour(), 0, 0, 0, time.UTC)
		end = start.Add(time.Hour)

	case "daily":
		start = time.Date(t.Year(), t.Month(), t.Day(), 0, 0, 0, 0, time.UTC)
		end = start.AddDate(0, 0, 1)

	case "weekly":
		// Roll back to Monday 00:00:00Z of this week.
		weekday := t.Weekday()
		if weekday == time.Sunday {
			weekday = 7
		}
		daysBack := int(weekday) - int(time.Monday)
		start = time.Date(t.Year(), t.Month(), t.Day()-daysBack, 0, 0, 0, 0, time.UTC)
		end = start.AddDate(0, 0, 7)

	case "monthly":
		start = time.Date(t.Year(), t.Month(), 1, 0, 0, 0, 0, time.UTC)
		end = start.AddDate(0, 1, 0)

	default:
		// Fallback to daily for unknown periods.
		start = time.Date(t.Year(), t.Month(), t.Day(), 0, 0, 0, 0, time.UTC)
		end = start.AddDate(0, 0, 1)
	}

	return start, end
}
