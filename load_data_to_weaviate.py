import weaviate
from weaviate.classes.init import Auth
from weaviate.classes.config import Configure, Property, DataType, ReferenceProperty
import json
import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Weaviate connection setup
weaviate_url = os.getenv("WEAVIATE_URL")
weaviate_key = os.getenv("WEAVIATE_API_KEY")

if not weaviate_url or not weaviate_key:
    raise ValueError("WEAVIATE_URL and WEAVIATE_API_KEY environment variables must be set")

def load_json_data():
    """Load data from JSON files"""
    with open('people.json', 'r') as f:
        people = json.load(f)
    
    with open('activities.json', 'r') as f:
        activities = json.load(f)
    
    with open('events.json', 'r') as f:
        events = json.load(f)
    
    return people, activities, events

def create_schemas(client):
    """Create Weaviate schemas for People, Activities, and Events"""
    
    # Delete existing collections if they exist
    if client.collections.exists("Person"):
        client.collections.delete("Person")
    if client.collections.exists("Activity"):
        client.collections.delete("Activity")
    if client.collections.exists("Event"):
        client.collections.delete("Event")
    
    # Create Person collection
    person_collection = client.collections.create(
        name="Person",
        properties=[
            Property(name="name", data_type=DataType.TEXT),
            Property(name="gender", data_type=DataType.TEXT),
            Property(name="birth_date", data_type=DataType.DATE)
        ]
    )
    
    # Create Activity collection
    activity_collection = client.collections.create(
        name="Activity",
        properties=[
            Property(name="name", data_type=DataType.TEXT),
            Property(name="type", data_type=DataType.TEXT),
            Property(name="indoor", data_type=DataType.BOOL),
            Property(name="outdoor", data_type=DataType.BOOL)
        ]
    )
    
    # Create Event collection
    event_collection = client.collections.create(
        name="Event",
        properties=[
            Property(name="name", data_type=DataType.TEXT),
            Property(name="activity_name", data_type=DataType.TEXT),
            Property(name="date_time", data_type=DataType.DATE),
            Property(name="people", data_type=DataType.TEXT_ARRAY)
        ],
        references=[
            ReferenceProperty(name="activity", target_collection="Activity"),
            ReferenceProperty(name="attendees", target_collection="Person")
        ]
    )
    
    return person_collection, activity_collection, event_collection

def insert_people(client, people_data):
    """Insert people data into Weaviate"""
    person_collection = client.collections.get("Person")
    person_uuids = {}
    
    for person in people_data:
        # Convert birth_date string to datetime object
        birth_date = datetime.strptime(person['birth_date'], '%Y-%m-%d')
        
        result = person_collection.data.insert(
            properties={
                "name": person['name'],
                "gender": person['gender'],
                "birth_date": birth_date
            }
        )
        person_uuids[person['name']] = result
        print(f"Inserted person: {person['name']}")
    
    return person_uuids

def insert_activities(client, activities_data):
    """Insert activities data into Weaviate"""
    activity_collection = client.collections.get("Activity")
    activity_uuids = {}
    
    for activity in activities_data:
        result = activity_collection.data.insert(
            properties={
                "name": activity['name'],
                "type": activity['type'],
                "indoor": activity['indoor'],
                "outdoor": activity['outdoor']
            }
        )
        activity_uuids[activity['name']] = result
        print(f"Inserted activity: {activity['name']}")
    
    return activity_uuids

def insert_events(client, events_data, person_uuids, activity_uuids):
    """Insert events data into Weaviate with references"""
    event_collection = client.collections.get("Event")
    
    for event in events_data:
        # Convert date_time string to datetime object
        event_datetime = datetime.fromisoformat(event['date_time'])
        
        # Get attendee UUIDs
        attendee_uuids = [person_uuids[name] for name in event['people'] if name in person_uuids]
        
        # Get activity UUID
        activity_uuid = activity_uuids.get(event['activity'])
        
        result = event_collection.data.insert(
            properties={
                "name": event['name'],
                "activity_name": event['activity'],
                "date_time": event_datetime,
                "people": event['people']
            },
            references={
                "activity": activity_uuid,
                "attendees": attendee_uuids
            }
        )
        print(f"Inserted event: {event['name']}")

def main():
    """Main function to load all data into Weaviate"""
    # Connect to Weaviate
    client = weaviate.connect_to_weaviate_cloud(
        cluster_url=weaviate_url,
        auth_credentials=Auth.api_key(weaviate_key),
    )
    
    try:
        print("Connected to Weaviate:", client.is_ready())
        
        # Load JSON data
        print("Loading JSON data...")
        people, activities, events = load_json_data()
        
        # Create schemas
        print("Creating schemas...")
        create_schemas(client)
        
        # Insert data
        print("Inserting people...")
        person_uuids = insert_people(client, people)
        
        print("Inserting activities...")
        activity_uuids = insert_activities(client, activities)
        
        print("Inserting events...")
        insert_events(client, events, person_uuids, activity_uuids)
        
        print("Data insertion completed successfully!")
        
        # Query to verify data
        person_collection = client.collections.get("Person")
        activity_collection = client.collections.get("Activity")
        event_collection = client.collections.get("Event")
        
        print(f"\nData summary:")
        print(f"People: {person_collection.aggregate.over_all().total_count}")
        print(f"Activities: {activity_collection.aggregate.over_all().total_count}")
        print(f"Events: {event_collection.aggregate.over_all().total_count}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    main()