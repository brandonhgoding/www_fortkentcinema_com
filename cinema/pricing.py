from .models import TicketRate, RateTypes


def get_rate_for_screening(screening_time) -> TicketRate:
    # If you later add explicit rate_type on Booking/ScreeningTime, check that first.
    if screening_time.is_matinee:
        rate_type = RateTypes.MATINEE
    else:
        rate_type = RateTypes.EVENING_ADMISSION

    try:
        return TicketRate.objects.get(rate_type=rate_type)
    except TicketRate.DoesNotExist:
        # Fallback: GA or bust; tune to your liking
        return TicketRate.objects.get(rate_type=RateTypes.EVENING_ADMISSION)
