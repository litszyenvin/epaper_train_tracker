import requests
import json
from datetime import datetime
import time

def collect_train_data(number_of_trains, url, username, password, max_retries=3, retry_delay=2):
    # Create a session object
    session = requests.Session()
    # Set up the HTTP Basic authentication credentials
    session.auth = (username, password)

    for attempt in range(max_retries):
        try:
            # Send a GET request to the HTTPS endpoint
            response = session.get(url)
            # Check if the request was successful (status code 200)
            if response.status_code == 200:
                # Parse the JSON response
                data = json.loads(response.text)
                # Initialize an empty list to store train details
                train_details = []

                services = data['services']
                count = 0
                for service in services:
                    locationDetail = service['locationDetail']
                    serviceUid = service['serviceUid']
                    runDate = service['runDate']

                    departureIsRealtime = False
                    serviceIsCancelled = False
                    if 'cancelReasonCode' in locationDetail:
                        departureTime = locationDetail['gbttBookedArrival']
                        serviceIsCancelled = True
                    elif 'realtimeDeparture' in locationDetail:
                        departureTime = locationDetail['realtimeArrival']
                        departureIsRealtime = True
                    else:
                        departureTime = locationDetail['gbttBookedArrival']

                    departurePlatform = locationDetail['platform']

                    try:
                        next_day = locationDetail['gbttBookedDepartureNextDay']
                    except:
                        next_day = False

                    if is_later_than_current_time(departureTime) or next_day == True:
                        # Extract relevant information
                        train_info = {
                            "destination": locationDetail['destination'][0]['description'],
                            "departure_status": "Scheduled" if not departureIsRealtime and not serviceIsCancelled else ("Live" if departureIsRealtime else "Cancelled"),
                            "departure_time": departureTime,
                            "departure_platform": departurePlatform
                        }

                        # Get further information for arrival time and journey length
                        train_service_url = f"https://api.rtt.io/api/v1/json/service/{serviceUid}/{runDate[:4]}/{runDate[5:7]}/{runDate[8:10]}"
                        ftrain_service_response = session.get(train_service_url)
                        train_services_data = json.loads(ftrain_service_response.text)

                        # Check if 'locations' field is present
                        if 'locations' in train_services_data:
                            locations = train_services_data['locations']
                            for location in locations:
                                if location['description'] == "St Pancras International":
                                    if 'realtimeArrival' in location:
                                        arrivalTime = location['realtimeArrival']
                                    else:
                                        arrivalTime = location['gbttBookedArrival']
                                    
                                    journeyLength = calculate_elapsed_minutes(departureTime, arrivalTime)

                                    # Add arrival time and journey length to train info
                                    train_info["arrival_time"] = arrivalTime
                                    train_info["journey_length"] = journeyLength

                                    break  # Break after finding arrival info

                        # Append train info to the list
                        train_details.append(train_info)
                        count += 1
                        if count == number_of_trains:
                            break

                return train_details

            else:
                # Print an error message
                print(f"Request failed with status code {response.status_code}")

        except requests.exceptions.RequestException as e:
            # Print the error message
            print(f"Attempt {attempt+1}/{max_retries}: An error occurred: {e}")

            # Wait before retrying
            time.sleep(retry_delay)

    # Return empty list if max retries reached
    else:
        return []

def calculate_elapsed_minutes(start, end):
    start_hours = int(start[:2])
    start_minutes = int(start[2:])
    end_hours = int(end[:2])
    end_minutes = int(end[2:])

    if start_hours == 23 and end_hours < 1:
        end_hours += 24

    start_total_minutes = start_hours * 60 + start_minutes
    end_total_minutes = end_hours * 60 + end_minutes

    elapsed_minutes = end_total_minutes - start_total_minutes

    return elapsed_minutes

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
    destination = 'STP'
    username = "rttapi_litszyenvin"
    password = "bec5d38d598f2a3518962fedf8345569696cb0bf"
    number_of_trains = 4

    current_datetime = datetime.now()
    formatted_datetime = current_datetime.strftime("%Y/%m/%d/%H%M")
    url = url_head + origin + '/to/' + destination +'/'+ formatted_datetime
    # url = 'https://api.rtt.io/api/v1/json/search/SAC/to/STP/2024/02/21/1310'
    train_data = collect_train_data(number_of_trains, url, username, password)

    if train_data:
        print("Train information:")
        for train in train_data:
            print(f"Destination: {train['destination']},Plat {train['departure_platform']}")
            # Modified formatting for desired output
            print(f"{train['departure_time']}---->{train['arrival_time']} ({train['journey_length']} minutes) [{train['departure_status']}]")
    else:
        print("Error retrieving train information.")


