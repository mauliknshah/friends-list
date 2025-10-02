import weaviate
from weaviate.classes.init import Auth
from weaviate.classes.query import QueryReference
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Weaviate connection setup
weaviate_url = os.getenv("WEAVIATE_URL")
weaviate_key = os.getenv("WEAVIATE_API_KEY")

if not weaviate_url or not weaviate_key:
    raise ValueError("WEAVIATE_URL and WEAVIATE_API_KEY environment variables must be set")

def print_all_people(client):
    """Fetch and print all people from Weaviate"""
    print("\n" + "="*50)
    print("PEOPLE")
    print("="*50)
    
    person_collection = client.collections.get("Person")
    
    try:
        response = person_collection.query.fetch_objects(limit=100)
        
        if response.objects:
            for i, person in enumerate(response.objects, 1):
                print(f"{i}. Name: {person.properties['name']}")
                print(f"   Gender: {person.properties['gender']}")
                print(f"   Birth Date: {person.properties['birth_date']}")
                print(f"   UUID: {person.uuid}")
                print("-" * 30)
        else:
            print("No people found.")
    except Exception as e:
        print(f"Error fetching people: {e}")

def print_all_activities(client):
    """Fetch and print all activities from Weaviate"""
    print("\n" + "="*50)
    print("ACTIVITIES")
    print("="*50)
    
    activity_collection = client.collections.get("Activity")
    
    try:
        response = activity_collection.query.fetch_objects(limit=100)
        
        if response.objects:
            for i, activity in enumerate(response.objects, 1):
                print(f"{i}. Name: {activity.properties['name']}")
                print(f"   Type: {activity.properties['type']}")
                print(f"   Indoor: {activity.properties['indoor']}")
                print(f"   Outdoor: {activity.properties['outdoor']}")
                print(f"   UUID: {activity.uuid}")
                print("-" * 30)
        else:
            print("No activities found.")
    except Exception as e:
        print(f"Error fetching activities: {e}")

def print_all_events(client):
    """Fetch and print all events from Weaviate with references"""
    print("\n" + "="*50)
    print("EVENTS")
    print("="*50)
    
    event_collection = client.collections.get("Event")
    
    try:
        response = event_collection.query.fetch_objects(
            limit=100,
            return_references=[QueryReference(
            link_on="activity",           # The reference property name   # Properties to retrieve from the referenced object
        ), QueryReference(
            link_on="attendees",
        )]
        )
        
        if response.objects:
            for i, event in enumerate(response.objects, 1):
                print(f"{i}. Event: {event.properties['name']}")
                print(f"   Activity: {event.properties['activity_name']}")
                print(f"   Date/Time: {event.properties['date_time']}")
                print(f"   People: {', '.join(event.properties['people'])}")
                print(f"   UUID: {event.uuid}")
                
                # Print referenced activity details
                if hasattr(event, 'references') and event.references and 'activity' in event.references:
                    activity_ref = event.references['activity']
                    if activity_ref.objects:
                        activity = activity_ref.objects[0]
                        print(f"   Referenced Activity: {activity.properties['name']}")

                # Print referenced attendee details
                if hasattr(event, 'references') and event.references and 'attendees' in event.references:
                    attendees_ref = event.references['attendees']
                    if attendees_ref.objects:
                        attendee_names = [att.properties['name'] for att in attendees_ref.objects]
                        print(f"   Referenced Attendees: {', '.join(attendee_names)}")
                
                print("-" * 30)
        else:
            print("No events found.")
    except Exception as e:
        print(f"Error fetching events: {e}")

def print_collection_counts(client):
    """Print count of objects in each collection"""
    print("\n" + "="*50)
    print("COLLECTION SUMMARY")
    print("="*50)
    
    try:
        person_collection = client.collections.get("Person")
        activity_collection = client.collections.get("Activity")
        event_collection = client.collections.get("Event")
        
        person_count = person_collection.aggregate.over_all().total_count
        activity_count = activity_collection.aggregate.over_all().total_count
        event_count = event_collection.aggregate.over_all().total_count
        
        print(f"Total People: {person_count}")
        print(f"Total Activities: {activity_count}")
        print(f"Total Events: {event_count}")
        
    except Exception as e:
        print(f"Error getting collection counts: {e}")

def search_events_by_activity(client, activity_name):
    """Search for events by activity name"""
    print(f"\n" + "="*50)
    print(f"EVENTS FOR ACTIVITY: {activity_name.upper()}")
    print("="*50)
    
    event_collection = client.collections.get("Event")
    
    try:
        response = event_collection.query.bm25(
            query=activity_name,
            query_properties=["activity_name"],
            limit=10
        )
        
        if response.objects:
            for i, event in enumerate(response.objects, 1):
                print(f"{i}. {event.properties['name']}")
                print(f"   Activity: {event.properties['activity_name']}")
                print(f"   Date: {event.properties['date_time']}")
                print(f"   Attendees: {', '.join(event.properties['people'])}")
                print("-" * 30)
        else:
            print(f"No events found for activity: {activity_name}")
    except Exception as e:
        print(f"Error searching events: {e}")

def main():
    """Main function to fetch and display all data from Weaviate"""
    # Connect to Weaviate
    client = weaviate.connect_to_weaviate_cloud(
        cluster_url=weaviate_url,
        auth_credentials=Auth.api_key(weaviate_key),
    )
    
    try:
        print("Connected to Weaviate:", client.is_ready())
        
        # Print collection counts
        print_collection_counts(client)
        
        # Print all data
        print_all_people(client)
        print_all_activities(client)
        print_all_events(client)
        
        # Example search
        search_events_by_activity(client, "Salsa Dancing")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    main()