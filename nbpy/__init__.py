"""NBPy package."""

import requests
from decimal import Decimal
from functools import lru_cache
from .version import version as __version__
from .errors import UnknownCurrencyCode, APIError
from .utils import validate_date, first_if_sequence
from .currencies import currencies
from .exchange_rate import NBPExchangeRate


__all__ = ['NBPClient']


#: Base URI
BASE_URI = "http://api.nbp.pl/api"


class NBPClient(object):
    """Converter between PLN and other currencies."""

    # Template URI for NBP API calls
    _uri_template = BASE_URI + "/exchangerates/rates/{table}/{code}/{tail}"

    def __init__(self, currency_code, **kwargs):
        """
        Initialize for given `currency_code` and `amount`.
        """
        self.currency_code = currency_code

        #: If True, values will be floats instead of decimals.
        self.as_float = kwargs.get('as_float', False)

        #: If True, instead of raising APIErrors return None
        self.suppress_api_errors = kwargs.get('suppress_api_errors', False)

        #: Max size for LRU cache.
        self._cache_size = kwargs.get('cache_size', 128)

        cache_decorator = lru_cache(maxsize=self.cache_size)
        self._get_response_data = cache_decorator(self._get_response_data)

    def __repr__(self):
        return "{cls_name}({code}, as_float={as_float!s}, suppress_api_errors={suppress_api_errors!s}, cache_size={cache_size})".format(
            cls_name=self.__class__.__name__,
            code=self.currency_code,
            as_float=self.as_float,
            suppress_api_errors=self.suppress_api_errors,
            cache_size=self.cache_size
        )

    @property
    def currency_code(self):
        return self._currency_code

    @currency_code.setter
    def currency_code(self, code):
        code = code.upper()
        if code not in currencies:
            raise UnknownCurrencyCode(code)
        self._currency_code = code

    @property
    def cache_size(self):
        """Read-only LRU cache size."""
        return self._cache_size

    def _get_response_data(self, uri_tail, all_values=False):
        """Return HTTP response data from API call."""
        tables = currencies[self.currency_code].tables.copy()
        if not all_values:
            # Avoid bid/ask values
            tables.discard('C')

        rates = {}

        for table in tables:
            uri = self._uri_template.format(
                code=self.currency_code.lower(),
                table=table.lower(),
                tail=uri_tail.lower()
            )

            # Send request to API, raise exception on error
            try:
                headers = {'Accept': 'application/json'}
                r = requests.get(uri, headers=headers)
                r.raise_for_status()
            except Exception as e:
                if self.suppress_api_errors:
                    # Return None if errors suppressed
                    return None
                raise APIError(str(e))

            # Parse data with values as decimals
            if self.as_float:
                parse_float_cls = float
            else:
                parse_float_cls = Decimal

            _data = r.json(parse_float=parse_float_cls)['rates']
            _data = {rate['effectiveDate']: rate for rate in _data}
            for date in _data:
                if date in rates:
                    rates[date].update(_data[date])
                else:
                    rates[date] = _data[date]

        return sorted([
            NBPExchangeRate(
                currency_code=self.currency_code,
                date=rate['effectiveDate'],
                **rate
            ) for rate in rates.values() if 'mid' in rate
        ], key=lambda rate: rate.date)

    @first_if_sequence
    def current(self, all_values=False):
        return self._get_response_data('', all_values)

    @first_if_sequence
    def today(self, all_values=False):
        return self._get_response_data('today', all_values)

    def last(self, n, all_values=False):
        uri_tail = "last/{:d}".format(n)
        return self._get_response_data(uri_tail, all_values)

    @first_if_sequence
    def date(self, date, all_values=False):
        validate_date(date)

        return self._get_response_data(date, all_values)

    def date_range(self, start_date, end_date, all_values=False):
        validate_date(start_date)
        validate_date(end_date)

        uri_tail = "{}/{}".format(start_date, end_date)
        return self._get_response_data(uri_tail, all_values)

    def __call__(self, all_values=False):
        return self.current(all_values)