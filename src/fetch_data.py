import os
import json
import time
import logging
import requests
from datetime import datetime
import tempfile

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# List of 5 rotating US cities with their states and representative ZIP codes
CITIES = [
    {"city": "Austin", "state": "TX", "zip": "78701"},
    {"city": "Phoenix", "state": "AZ", "zip": "85016"},
    {"city": "Miami", "state": "FL", "zip": "33130"},
    {"city": "Nashville", "state": "TN", "zip": "37203"},
    {"city": "Charlotte", "state": "NC", "zip": "28202"}
]

def get_current_city():
    """Rotate through the 5 cities based on the day of the year."""
    yday = datetime.now().timetuple().tm_yday
    city_info = CITIES[yday % 5]
    logger.info(f"Day of year: {yday}. Selected city: {city_info['city']}, {city_info['state']} (Zip: {city_info['zip']})")
    return city_info

def get_cache_path(city, request_type):
    """Get cross-platform cache file path for /tmp/cache_{city}_{request_type}_{date}.json."""
    tmp_dir = "/tmp" if os.path.exists("/tmp") and os.access("/tmp", os.W_OK) else tempfile.gettempdir()
    date_str = datetime.now().strftime("%Y-%m-%d")
    clean_city = city.replace(" ", "_").lower()
    return os.path.join(tmp_dir, f"cache_{clean_city}_{request_type}_{date_str}.json")

def get_api_headers():
    """Get authorization headers for Rentcast API."""
    api_key = os.environ.get("RENTCAST_API_KEY")
    if not api_key:
        logger.warning("RENTCAST_API_KEY environment variable is not set. API calls will fail.")
        return None
    return {
        "X-Api-Key": api_key,
        "Accept": "application/json"
    }

def make_api_request(url, params=None):
    """Make HTTP GET request with retries and exponential backoff."""
    headers = get_api_headers()
    if not headers:
        raise ValueError("Missing API Key. Cannot complete API request.")

    max_retries = 3
    backoff = 2.0  # seconds

    for attempt in range(max_retries):
        try:
            logger.info(f"API Request to URL: {url} (Params: {params}), Attempt {attempt + 1}")
            response = requests.get(url, headers=headers, params=params, timeout=15)
            
            # If rate limited (429) or server error, retry
            if response.status_code in [429, 500, 502, 503, 504]:
                logger.warning(f"Got response status {response.status_code}. Retrying...")
                time.sleep(backoff * (2 ** attempt))
                continue
                
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.warning(f"HTTP request error: {e}")
            if attempt == max_retries - 1:
                raise e
            time.sleep(backoff * (2 ** attempt))
            
    raise Exception("API request failed after maximum retries.")

def get_mock_market_stats(city, state):
    """Fallback mock data for testing and when API keys are missing/exhausted."""
    logger.info(f"Returning Mock Market Stats for {city}, {state}")
    mock_prices = {"Austin": 540000, "Phoenix": 435000, "Miami": 595000, "Nashville": 470000, "Charlotte": 395000}
    mock_rents = {"Austin": 2200, "Phoenix": 1850, "Miami": 2700, "Nashville": 2100, "Charlotte": 1800}
    mock_mom_sale = {"Austin": -0.012, "Phoenix": 0.005, "Miami": 0.018, "Nashville": -0.002, "Charlotte": 0.008}
    mock_mom_rent = {"Austin": -0.008, "Phoenix": 0.012, "Miami": 0.025, "Nashville": 0.004, "Charlotte": 0.015}
    
    city_price = mock_prices.get(city, 450000)
    city_rent = mock_rents.get(city, 2000)
    
    return {
        "city": city,
        "state": state,
        "medianPrice": city_price,
        "medianRent": city_rent,
        "saleMoM": mock_mom_sale.get(city, 0.005),
        "rentalMoM": mock_mom_rent.get(city, 0.005),
        "totalListings": 1245,
        "newListings": 87
    }

def get_mock_listings(city, state):
    """Fallback mock listings for testing."""
    logger.info(f"Returning Mock Active Listings for {city}, {state}")
    return [
        {"formattedAddress": "104 Maple Ave, " + city, "price": 425000, "bedrooms": 3, "bathrooms": 2, "squareFootage": 1650},
        {"formattedAddress": "890 Pine St, " + city, "price": 615000, "bedrooms": 4, "bathrooms": 2.5, "squareFootage": 2200},
        {"formattedAddress": "23 Oak Dr, " + city, "price": 310000, "bedrooms": 2, "bathrooms": 1.5, "squareFootage": 1100},
        {"formattedAddress": "402 Cedar Ln, " + city, "price": 825000, "bedrooms": 5, "bathrooms": 4, "squareFootage": 3400},
        {"formattedAddress": "15 Elm Ct, " + city, "price": 500000, "bedrooms": 3, "bathrooms": 2, "squareFootage": 1800}
    ]

def get_mock_rental_trends(zipcode):
    """Fallback mock rental trends."""
    logger.info(f"Returning Mock Rental Trends for zip {zipcode}")
    return [
        {"bedrooms": 0, "averageRent": 1200},
        {"bedrooms": 1, "averageRent": 1500},
        {"bedrooms": 2, "averageRent": 1900},
        {"bedrooms": 3, "averageRent": 2400},
        {"bedrooms": 4, "averageRent": 3000}
    ]

def get_market_stats(city, state):
    """
    Fetch market stats for city and state.
    Calls GET /v1/markets?city={city}&state={state}&dataType=All
    If the API fails because of missing zipCode parameter, falls back to the representative ZIP code.
    Returns median sale price, median rent, and month-over-month changes.
    """
    cache_file = get_cache_path(city, "stats")
    
    # 1. Check local cache
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                logger.info(f"Cache hit: Loading stats for {city} from {cache_file}")
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read cache file {cache_file}: {e}")

    # 2. Check if API key is present, if not use Mock data
    if not os.environ.get("RENTCAST_API_KEY"):
        data = get_mock_market_stats(city, state)
        # Store mock data in cache so pipeline runs identically
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning(f"Failed to write mock data to cache: {e}")
        return data

    # 3. Call API with city and state
    url = "https://api.rentcast.io/v1/markets"
    params = {"city": city, "state": state, "dataType": "All", "historyRange": 12}
    
    try:
        raw_data = make_api_request(url, params)
    except Exception as e:
        logger.warning(f"Query by city/state failed: {e}. Trying fallback ZIP code.")
        # Fallback to ZIP code query
        city_zip = next((c["zip"] for c in CITIES if c["city"].lower() == city.lower()), "78701")
        try:
            params = {"zipCode": city_zip, "dataType": "All", "historyRange": 12}
            raw_data = make_api_request(url, params)
        except Exception as ex:
            logger.error(f"Fallback ZIP query failed: {ex}. Using mock stats.")
            return get_mock_market_stats(city, state)

    # 4. Parse API responses and calculate MoM change
    sale_data = raw_data.get("saleData", {})
    rental_data = raw_data.get("rentalData", {})
    
    median_price = sale_data.get("medianPrice", 0)
    median_rent = rental_data.get("medianRent", 0)
    
    # Calculate Sale MoM change
    sale_mom = 0.0
    sale_history = sale_data.get("history", {})
    if isinstance(sale_history, dict) and len(sale_history) >= 2:
        sorted_months = sorted(sale_history.keys())
        latest_month = sorted_months[-1]
        prev_month = sorted_months[-2]
        
        latest_p = sale_history[latest_month].get("medianPrice", 0)
        prev_p = sale_history[prev_month].get("medianPrice", 0)
        if prev_p > 0:
            sale_mom = (latest_p - prev_p) / prev_p

    # Calculate Rental MoM change
    rental_mom = 0.0
    rental_history = rental_data.get("history", {})
    if isinstance(rental_history, dict) and len(rental_history) >= 2:
        sorted_months = sorted(rental_history.keys())
        latest_month = sorted_months[-1]
        prev_month = sorted_months[-2]
        
        latest_r = rental_history[latest_month].get("medianRent", 0)
        prev_r = rental_history[prev_month].get("medianRent", 0)
        if prev_r > 0:
            rental_mom = (latest_r - prev_r) / prev_r

    result = {
        "city": city,
        "state": state,
        "medianPrice": median_price or get_mock_market_stats(city, state)["medianPrice"],
        "medianRent": median_rent or get_mock_market_stats(city, state)["medianRent"],
        "saleMoM": sale_mom,
        "rentalMoM": rental_mom,
        "totalListings": sale_data.get("totalListings", 0),
        "newListings": sale_data.get("newListings", 0)
    }

    # Save to cache
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(result, f)
    except Exception as e:
        logger.warning(f"Failed to cache stats: {e}")

    return result

def get_hot_listings(city, state, limit=5):
    """
    Fetch hot listings for city and state.
    Calls GET /v1/listings/sale?city={city}&state={state}&status=Active&limit={limit}&sort=listedDate&sortDirection=desc
    """
    cache_file = get_cache_path(city, "listings")
    
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                logger.info(f"Cache hit: Loading listings for {city} from {cache_file}")
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read listings cache: {e}")

    if not os.environ.get("RENTCAST_API_KEY"):
        data = get_mock_listings(city, state)
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning(f"Failed to write mock listings to cache: {e}")
        return data

    url = "https://api.rentcast.io/v1/listings/sale"
    params = {
        "city": city,
        "state": state,
        "status": "Active",
        "limit": limit,
        "sort": "listedDate",
        "sortDirection": "desc"
    }

    try:
        raw_listings = make_api_request(url, params)
    except Exception as e:
        logger.error(f"Failed to fetch listings: {e}. Using mock listings.")
        return get_mock_listings(city, state)

    processed = []
    for item in raw_listings:
        processed.append({
            "formattedAddress": item.get("formattedAddress", "Unknown Address"),
            "price": item.get("price", 0),
            "bedrooms": item.get("bedrooms", 0),
            "bathrooms": item.get("bathrooms", 0),
            "squareFootage": item.get("squareFootage", 0)
        })

    # Save to cache
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(processed, f)
    except Exception as e:
        logger.warning(f"Failed to cache listings: {e}")

    return processed

def get_rental_trends(zipcode):
    """
    Fetch rental trends by zipcode.
    Calls GET /v1/markets?zipCode={zipcode}&dataType=Rental
    """
    cache_file = get_cache_path(zipcode, "rental_trends")
    
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                logger.info(f"Cache hit: Loading rental trends for zip {zipcode} from {cache_file}")
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read rental trends cache: {e}")

    if not os.environ.get("RENTCAST_API_KEY"):
        data = get_mock_rental_trends(zipcode)
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning(f"Failed to write mock rental trends to cache: {e}")
        return data

    url = "https://api.rentcast.io/v1/markets"
    params = {"zipCode": zipcode, "dataType": "Rental", "historyRange": 6}

    try:
        raw_data = make_api_request(url, params)
    except Exception as e:
        logger.error(f"Failed to fetch rental trends for zip {zipcode}: {e}. Using mock trends.")
        return get_mock_rental_trends(zipcode)

    rental_data = raw_data.get("rentalData", {})
    beds_data = rental_data.get("dataByBedrooms", [])
    
    processed = []
    for item in beds_data:
        processed.append({
            "bedrooms": item.get("bedrooms", 0),
            "averageRent": item.get("averageRent", 0)
        })

    # If no beds data was found, use mock values
    if not processed:
        processed = get_mock_rental_trends(zipcode)

    # Save to cache
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(processed, f)
    except Exception as e:
        logger.warning(f"Failed to cache rental trends: {e}")

    return processed
