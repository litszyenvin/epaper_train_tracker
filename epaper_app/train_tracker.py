import requests
import json
import re
from datetime import datetime
import time

def collect_train_data(number_of_trains, url, username, password, destination_code=None, max_retries=3, retry_delay=2):
    session = requests.Session()
    session.auth = (username, password)
    session.headers.update({"Accept": "application/json"})

    if not destination_code:
        m = re.search(r"/to/([^/]+)/", url)
        if m:
            destination_code = m.group(1)

    for attempt in range(max_retries):
        try:
            response = session.get(url, timeout=15)
            if response.status_code == 200:
                try:
                    data = response.json()
                except Exception:
                    data = json.loads(response.text)

                services = data.get('services') or []
                if not services:
                    print("No services returned for this query.")
                    return []

                train_details = []
                count = 0

                for service in services:
                    try:
                        locationDetail = service.get('locationDetail') or {}
                        serviceUid = service.get('serviceUid')
                        runDate = service.get('runDate')

                        if not serviceUid or not runDate or not locationDetail:
                            continue

                        departureIsRealtime = False
                        serviceIsCancelled = False

                        if 'cancelReasonCode' in locationDetail:
                            departureTime = locationDetail.get('gbttBookedDeparture')
                            serviceIsCancelled = True
                        elif 'realtimeDeparture' in locationDetail:
                            departureTime = locationDetail.get('realtimeDeparture')
                            departureIsRealtime = True
                        else:
                            departureTime = locationDetail.get('gbttBookedDeparture')

                        if not (isinstance(departureTime, str) and len(departureTime) >= 4):
                            continue

                        departurePlatform = locationDetail.get('platform')
                        next_day = bool(locationDetail.get('gbttBookedDepartureNextDay', False))

                        if is_later_than_current_time(departureTime) or next_day is True:
                            destination_desc = "Unknown"
                            dest_list = locationDetail.get('destination') or []
                            if dest_list and isinstance(dest_list[0], dict):
                                destination_desc = dest_list[0].get('description', 'Unknown')

                            train_info = {
                                "destination": destination_desc,
                                "departure_status": (
                                    "Scheduled"
                                    if not departureIsRealtime and not serviceIsCancelled
                                    else ("Live" if departureIsRealtime else "Cancelled")
                                ),
                                "departure_time": departureTime,
                                "departure_platform": departurePlatform
                            }

                            train_service_url = (
                                f"https://api.rtt.io/api/v1/json/service/"
                                f"{serviceUid}/{runDate[:4]}/{runDate[5:7]}/{runDate[8:10]}"
                            )

                            ftrain_service_response = session.get(train_service_url, timeout=15)
                            if ftrain_service_response.status_code != 200:
                                print(f"Detail fetch failed: {ftrain_service_response.status_code} for {train_service_url}")
                                continue

                            try:
                                train_services_data = ftrain_service_response.json()
                            except Exception:
                                try:
                                    train_services_data = json.loads(ftrain_service_response.text)
                                except Exception:
                                    train_services_data = {}

                            locations = train_services_data.get('locations') or []
                            if not isinstance(locations, list) or not locations:
                                continue

                            arrivalTime = None
                            dest_code = (destination_code or "").upper()
                            for location in locations:
                                for code_field in ('crs', 'crsCode', 'stationCode', 'tiploc', 'locationCode', 'location_code'):
                                    val = location.get(code_field)
                                    if isinstance(val, str) and dest_code and val.upper() == dest_code:
                                        arrivalTime = location.get('realtimeArrival') or location.get('gbttBookedArrival')
                                        break
                                if arrivalTime:
                                    break

                            if not arrivalTime:
                                for location in locations:
                                    if destination_desc and isinstance(location.get('description'), str) and location.get('description') == destination_desc:
                                        arrivalTime = location.get('realtimeArrival') or location.get('gbttBookedArrival')
                                        break

                            if not (isinstance(arrivalTime, str) and len(arrivalTime) >= 4):
                                continue

                            journeyLength = calculate_elapsed_minutes(departureTime, arrivalTime)

                            train_info["arrival_time"] = arrivalTime
                            train_info["journey_length"] = journeyLength

                            train_details.append(train_info)
                            count += 1
                            if count == number_of_trains:
                                return train_details

                    except Exception as e:
                        print(f"Skipped a service due to error: {e}")
                        continue

                return train_details

            else:
                print(f"Request failed with status code {response.status_code}")

        except requests.exceptions.RequestException as e:
            print(f"Attempt {attempt+1}/{max_retries}: An error occurred: {e}")
            time.sleep(retry_delay)

    else:
        return []


def calculate_elapsed_minutes(start, end):
    start_hours = int(start[:2])
    start_minutes = int(start[2:])
    end_hours = int(end[:2])
    end_minutes = int(end[2:])

    start_total = start_hours * 60 + start_minutes
    end_total = end_hours * 60 + end_minutes

    if end_total < start_total:
        end_total += 24 * 60

    return end_total - start_total


def is_later_than_current_time(hhmm_string):
    current_time = datetime.now().strftime("%H%M")
    hhmm_hours = int(hhmm_string[:2])
    hhmm_minutes = int(hhmm_string[2:])
    current_hours = int(current_time[:2])
    current_minutes = int(current_time[2:])

    if hhmm_hours > current_hours or (hhmm_hours == current_hours and hhmm_minutes > current_minutes):
        return True
    else:
        return False


if __name__ == "__main__":
    url_head = "https://api.rtt.io/api/v1/json/search/"
    origin = 'SAC'
    destination = 'ZFD'
    username = "rttapi_litszyenvin"
    password = "bec5d38d598f2a3518962fedf8345569696cb0bf"
    number_of_trains = 4

    current_datetime = datetime.now()
    formatted_datetime = current_datetime.strftime("%Y/%m/%d/%H%M")
    url = url_head + origin + '/to/' + destination + '/' + formatted_datetime

    train_data = collect_train_data(number_of_trains, url, username, password, destination)

    if train_data:
        print("Train information:")
        for train in train_data:
            dest = train.get('destination', 'Unknown')
            plat = train.get('departure_platform', '?')
            dep = train.get('departure_time', '????')
            arr = train.get('arrival_time', '????')
            jl = train.get('journey_length', '?')
            status = train.get('departure_status', '?')

            print(f"Destination: {dest}, Plat {plat}")
            print(f"{dep}---->{arr} ({jl} minutes) [{status}]")
    else:
        print("No train information found or error retrieving train information.")
