from flask import Flask, jsonify, render_template_string, request
from flask_cors import CORS
import weaviate
from weaviate.classes.init import Auth
from weaviate.classes.query import QueryReference
from datetime import datetime
import json
import os
from dotenv import load_dotenv
import anthropic

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
CORS(app)

# Weaviate connection setup
weaviate_url = os.getenv("WEAVIATE_URL")
weaviate_key = os.getenv("WEAVIATE_API_KEY")
anthropic_key = os.getenv("ANTHROPIC_API_KEY")

if not weaviate_url or not weaviate_key:
    raise ValueError("WEAVIATE_URL and WEAVIATE_API_KEY environment variables must be set")

if not anthropic_key:
    raise ValueError("ANTHROPIC_API_KEY environment variable must be set")

# Initialize Claude client
claude_client = anthropic.Anthropic(api_key=anthropic_key)

def get_weaviate_client():
    """Create and return Weaviate client"""
    return weaviate.connect_to_weaviate_cloud(
        cluster_url=weaviate_url,
        auth_credentials=Auth.api_key(weaviate_key),
    )

@app.route('/')
def index():
    """Serve the main HTML page"""
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/events')
def get_events():
    """Get all events with their details"""
    client = get_weaviate_client()
    try:
        event_collection = client.collections.get("Event")
        response = event_collection.query.fetch_objects(
            limit=100,
            return_references=[
                QueryReference(link_on="activity"),
                QueryReference(link_on="attendees")
            ]
        )
        
        events = []
        for event in response.objects:
            event_data = {
                'uuid': str(event.uuid),
                'name': event.properties['name'],
                'activity_name': event.properties['activity_name'],
                'date_time': event.properties['date_time'].isoformat() if event.properties['date_time'] else None,
                'people': event.properties['people'],
                'activity': None,
                'attendees': []
            }
            
            # Add referenced activity details
            if hasattr(event, 'references') and event.references and 'activity' in event.references:
                activity_ref = event.references['activity']
                if activity_ref.objects:
                    activity = activity_ref.objects[0]
                    event_data['activity'] = {
                        'uuid': str(activity.uuid),
                        'name': activity.properties['name'],
                        'type': activity.properties['type'],
                        'indoor': activity.properties['indoor'],
                        'outdoor': activity.properties['outdoor']
                    }
            
            # Add referenced attendee details
            if hasattr(event, 'references') and event.references and 'attendees' in event.references:
                attendees_ref = event.references['attendees']
                if attendees_ref.objects:
                    for attendee in attendees_ref.objects:
                        event_data['attendees'].append({
                            'uuid': str(attendee.uuid),
                            'name': attendee.properties['name'],
                            'gender': attendee.properties['gender'],
                            'birth_date': attendee.properties['birth_date'].isoformat() if attendee.properties['birth_date'] else None
                        })
            
            events.append(event_data)
        
        return jsonify(events)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        client.close()

@app.route('/api/activity/<activity_name>/events')
def get_events_by_activity(activity_name):
    """Get events count and list for a specific activity"""
    client = get_weaviate_client()
    try:
        event_collection = client.collections.get("Event")
        response = event_collection.query.bm25(
            query=activity_name,
            query_properties=["activity_name"],
            limit=100
        )
        
        events = []
        for event in response.objects:
            events.append({
                'uuid': str(event.uuid),
                'name': event.properties['name'],
                'date_time': event.properties['date_time'].isoformat() if event.properties['date_time'] else None,
                'people': event.properties['people']
            })
        
        return jsonify({
            'activity_name': activity_name,
            'event_count': len(events),
            'events': events
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        client.close()

@app.route('/api/best-friends')
def get_best_friends():
    """Get pairs of people who attended the most events together"""
    client = get_weaviate_client()
    try:
        event_collection = client.collections.get("Event")
        response = event_collection.query.fetch_objects(
            limit=100
        )
        
        # Count co-occurrences of people
        pair_counts = {}
        for event in response.objects:
            people = event.properties['people']
            # Generate all pairs from this event
            for i in range(len(people)):
                for j in range(i + 1, len(people)):
                    pair = tuple(sorted([people[i], people[j]]))
                    pair_counts[pair] = pair_counts.get(pair, 0) + 1
        
        # Sort pairs by count (descending)
        best_friends = sorted(pair_counts.items(), key=lambda x: x[1], reverse=True)
        
        # Format the response
        friends_list = []
        for (person1, person2), count in best_friends:
            friends_list.append({
                'person1': person1,
                'person2': person2,
                'events_together': count
            })
        
        return jsonify(friends_list)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        client.close()

@app.route('/api/person/<person_name>/events')
def get_events_by_person(person_name):
    """Get events attended by a specific person"""
    client = get_weaviate_client()
    try:
        event_collection = client.collections.get("Event")
        response = event_collection.query.bm25(
            query=person_name,
            query_properties=["people"],
            limit=100
        )
        
        events = []
        for event in response.objects:
            if person_name in event.properties['people']:
                events.append({
                    'uuid': str(event.uuid),
                    'name': event.properties['name'],
                    'activity_name': event.properties['activity_name'],
                    'date_time': event.properties['date_time'].isoformat() if event.properties['date_time'] else None,
                    'people': event.properties['people']
                })
        
        return jsonify({
            'person_name': person_name,
            'event_count': len(events),
            'events': events
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        client.close()

@app.route('/api/query', methods=['POST'])
def query_friends():
    """Handle natural language queries about friends and events"""
    client = get_weaviate_client()
    try:
        data = request.get_json()
        query = data.get('query', '').lower().strip()
        
        if not query:
            return jsonify({'error': 'Query is required'}), 400
        
        # Use Claude LLM for intelligent query processing
        response_data = process_query_with_claude(client, query)
        return jsonify(response_data)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        client.close()

def process_query_with_claude(client, query):
    """Process natural language queries using Claude LLM with event data context"""
    
    # Get all events, activities, and people data
    event_collection = client.collections.get("Event")
    events_response = event_collection.query.fetch_objects(limit=100)
    events = [event.properties for event in events_response.objects]
    
    activity_collection = client.collections.get("Activity")
    activities_response = activity_collection.query.fetch_objects(limit=100)
    activities = [activity.properties for activity in activities_response.objects]
    
    person_collection = client.collections.get("Person")
    people_response = person_collection.query.fetch_objects(limit=100)
    people = [person.properties for person in people_response.objects]
    
    # Prepare structured data context for Claude
    data_context = {
        "events": events,
        "activities": activities,
        "people": people
    }
    
    # Create analysis summary for Claude
    analysis_summary = create_data_analysis(events)
    
    # Construct prompt for Claude
    prompt = f"""You are an AI assistant helping users understand friendship and event data. You have access to data about people, their activities, and events they've attended together.

DATA CONTEXT:
{json.dumps(data_context, indent=2, default=str)}

ANALYSIS SUMMARY:
{analysis_summary}

USER QUESTION: "{query}"

Please provide a helpful, conversational response to the user's question based on the data above. Be specific with names, numbers, and details when possible. If you need to calculate relationships or statistics, do so based on the provided data.

Keep your response friendly and informative. Focus on answering the specific question asked."""

    try:
        # Call Claude API
        message = claude_client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=300,
            temperature=0.1,
            messages=[
                {
                    "role": "user", 
                    "content": prompt
                }
            ]
        )
        
        claude_response = message.content[0].text
        
        return {
            'answer': claude_response,
            'type': 'claude_response',
            'data': {}
        }
        
    except Exception as e:
        # Fallback to simple analysis if Claude API fails
        return fallback_query_analysis(events, query)

def create_data_analysis(events):
    """Create a summary analysis of the events data for Claude context"""
    
    # Count events per person
    person_counts = {}
    for event in events:
        for person in event['people']:
            person_counts[person] = person_counts.get(person, 0) + 1
    
    # Count events per activity
    activity_counts = {}
    for event in events:
        activity = event['activity_name']
        activity_counts[activity] = activity_counts.get(activity, 0) + 1
    
    # Find best friend pairs
    pair_counts = {}
    for event in events:
        people = event['people']
        for i in range(len(people)):
            for j in range(i + 1, len(people)):
                pair = tuple(sorted([people[i], people[j]]))
                pair_counts[pair] = pair_counts.get(pair, 0) + 1
    
    # Get top stats
    top_person = max(person_counts, key=person_counts.get) if person_counts else None
    top_activity = max(activity_counts, key=activity_counts.get) if activity_counts else None
    best_friends = max(pair_counts, key=pair_counts.get) if pair_counts else None
    
    best_friends_text = f"{best_friends[0]} & {best_friends[1]} ({pair_counts[best_friends]} events together)" if best_friends else "None calculated"
    recent_events = sorted([e['name'] for e in events if e.get('date_time')])[-3:] if events else []
    
    analysis = f"""
QUICK STATS:
- Total events: {len(events)}
- Total unique people: {len(person_counts)}
- Total unique activities: {len(activity_counts)}
- Most active person: {top_person} ({person_counts.get(top_person, 0)} events)
- Most popular activity: {top_activity} ({activity_counts.get(top_activity, 0)} events)
- Best friends: {best_friends_text}
- Recent events: {recent_events}
"""
    
    return analysis

def fallback_query_analysis(events, query):
    """Fallback analysis if Claude API is unavailable"""
    query_lower = query.lower()
    
    if 'best friends' in query_lower or 'together' in query_lower:
        pair_counts = {}
        for event in events:
            people = event['people']
            for i in range(len(people)):
                for j in range(i + 1, len(people)):
                    pair = tuple(sorted([people[i], people[j]]))
                    pair_counts[pair] = pair_counts.get(pair, 0) + 1
        
        if pair_counts:
            best_pair = max(pair_counts, key=pair_counts.get)
            return {
                'answer': f"{best_pair[0]} and {best_pair[1]} are the best friends with {pair_counts[best_pair]} events together.",
                'type': 'fallback',
                'data': {}
            }
    
    return {
        'answer': "I'm having trouble processing your question right now. Please try asking about specific people, activities, or events.",
        'type': 'fallback',
        'data': {}
    }

# HTML Template
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Friends List</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #f5f5f5;
            color: #333;
        }

        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 2rem;
            text-align: center;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }

        .header h1 {
            font-size: 2.5rem;
            margin-bottom: 0.5rem;
        }

        .header p {
            font-size: 1.1rem;
            opacity: 0.9;
        }

        .container {
            display: flex;
            max-width: 1400px;
            margin: 2rem auto;
            gap: 2rem;
            padding: 0 1rem;
        }

        .main-content {
            flex: 2;
        }

        .sidebar {
            flex: 1;
            background: white;
            padding: 1.5rem;
            border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            height: fit-content;
            position: sticky;
            top: 2rem;
        }

        .sidebar h3 {
            color: #667eea;
            margin-bottom: 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 2px solid #eee;
        }

        .sidebar-content {
            line-height: 1.6;
        }

        .query-section {
            margin-bottom: 3rem;
            background: white;
            border-radius: 12px;
            padding: 2rem;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }

        .query-section h2 {
            color: #333;
            margin-bottom: 1.5rem;
            font-size: 1.8rem;
            text-align: center;
        }

        .query-box {
            display: flex;
            gap: 1rem;
            margin-bottom: 1.5rem;
        }

        #query-input {
            flex: 1;
            padding: 1rem;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 1rem;
            outline: none;
            transition: border-color 0.2s ease;
        }

        #query-input:focus {
            border-color: #667eea;
        }

        #query-button {
            padding: 1rem 2rem;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 1rem;
            font-weight: bold;
            cursor: pointer;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }

        #query-button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 12px rgba(102, 126, 234, 0.3);
        }

        #query-button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }

        #query-response {
            min-height: 60px;
            padding: 1.5rem;
            background: #f8f9fa;
            border-radius: 8px;
            border-left: 4px solid #667eea;
            font-size: 1.1rem;
            line-height: 1.6;
            display: none;
        }

        #query-response.show {
            display: block;
            animation: fadeIn 0.3s ease-in;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(-10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .query-answer {
            color: #333;
            font-weight: 500;
        }

        .best-friends-section {
            margin-bottom: 3rem;
        }

        .best-friends-section h2 {
            color: #333;
            margin-bottom: 1.5rem;
            font-size: 1.8rem;
            text-align: center;
        }

        .events-section h2 {
            color: #333;
            margin-bottom: 1.5rem;
            font-size: 1.8rem;
            text-align: center;
        }

        .friends-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }

        .friend-pair {
            background: linear-gradient(135deg, #ffeaa7 0%, #fab1a0 100%);
            border-radius: 12px;
            padding: 1.5rem;
            text-align: center;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
            position: relative;
        }

        .friend-pair:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 15px rgba(0,0,0,0.15);
        }

        .friend-pair.gold {
            background: linear-gradient(135deg, #f7dc6f 0%, #f39c12 100%);
            border: 2px solid #d4af37;
        }

        .friend-pair.silver {
            background: linear-gradient(135deg, #d5dbdb 0%, #85929e 100%);
            border: 2px solid #566573;
        }

        .friend-pair.bronze {
            background: linear-gradient(135deg, #edbb99 0%, #cd6155 100%);
            border: 2px solid #a04000;
        }

        .friend-names {
            font-size: 1.2rem;
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 0.5rem;
        }

        .events-count {
            font-size: 2rem;
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 0.5rem;
        }

        .events-label {
            color: #34495e;
            font-weight: 500;
        }

        .rank-badge {
            position: absolute;
            top: -10px;
            right: -10px;
            width: 30px;
            height: 30px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            color: white;
            font-size: 1.2rem;
        }

        .rank-badge.gold {
            background: #d4af37;
        }

        .rank-badge.silver {
            background: #c0c0c0;
        }

        .rank-badge.bronze {
            background: #cd7f32;
        }

        .event-card {
            background: white;
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }

        .event-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 15px rgba(0,0,0,0.15);
        }

        .event-title {
            font-size: 1.3rem;
            font-weight: bold;
            color: #333;
            margin-bottom: 0.5rem;
        }

        .event-datetime {
            color: #666;
            font-size: 0.9rem;
            margin-bottom: 1rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .event-datetime::before {
            content: "📅";
        }

        .event-detail {
            margin: 0.5rem 0;
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
        }

        .event-label {
            font-weight: 600;
            color: #555;
            min-width: 80px;
        }

        .clickable-link {
            color: #667eea;
            text-decoration: none;
            font-weight: 500;
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            transition: all 0.2s ease;
            cursor: pointer;
            display: inline-block;
        }

        .clickable-link:hover {
            background-color: #667eea;
            color: white;
            transform: scale(1.05);
        }

        .activity-link {
            background-color: #e8f2ff;
            border: 1px solid #667eea;
        }

        .person-link {
            background-color: #f0f8e8;
            border: 1px solid #4caf50;
            color: #4caf50;
        }

        .person-link:hover {
            background-color: #4caf50;
            color: white;
        }

        .person-tags {
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            margin-top: 0.5rem;
        }

        .loading {
            text-align: center;
            padding: 2rem;
            color: #666;
        }

        .error {
            background-color: #ffe6e6;
            color: #d32f2f;
            padding: 1rem;
            border-radius: 8px;
            margin: 1rem 0;
        }

        .sidebar-event {
            background: #f8f9fa;
            padding: 1rem;
            border-radius: 8px;
            margin: 0.5rem 0;
            border-left: 4px solid #667eea;
        }

        .sidebar-event h4 {
            color: #333;
            margin-bottom: 0.5rem;
        }

        .sidebar-event p {
            color: #666;
            font-size: 0.9rem;
        }

        .count-badge {
            background: #667eea;
            color: white;
            padding: 0.2rem 0.8rem;
            border-radius: 20px;
            font-size: 0.9rem;
            font-weight: bold;
            display: inline-block;
            margin-bottom: 1rem;
        }

        @media (max-width: 768px) {
            .container {
                flex-direction: column;
            }
            
            .sidebar {
                order: -1;
                position: relative;
                top: 0;
            }

            .header h1 {
                font-size: 2rem;
            }

            .event-detail {
                flex-direction: column;
            }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>Friends List</h1>
        <p>Explore events, activities, and see who are the best friends!</p>
    </div>

    <div class="container">
        <div class="main-content">
            <div class="query-section">
                <h2>💬 Ask About Friends</h2>
                <div class="query-box">
                    <input type="text" id="query-input" placeholder="Ask me anything! e.g., 'Who are the best friends?' or 'Who attended the most events?'">
                    <button id="query-button">Ask</button>
                </div>
                <div id="query-response"></div>
            </div>
            
            <div class="best-friends-section">
                <h2>🏆 Best Friends List</h2>
                <div id="best-friends-container">
                    <div class="loading">Loading best friends...</div>
                </div>
            </div>
            
            <div class="events-section">
                <h2>📅 All Events</h2>
                <div id="events-container">
                    <div class="loading">Loading events...</div>
                </div>
            </div>
        </div>

        <div class="sidebar">
            <h3>Details</h3>
            <div id="sidebar-content" class="sidebar-content">
                <p>Click on an activity or person to see more details here.</p>
            </div>
        </div>
    </div>

    <script>
        let eventsData = [];
        let bestFriendsData = [];

        async function loadBestFriends() {
            try {
                const response = await fetch('/api/best-friends');
                bestFriendsData = await response.json();
                renderBestFriends(bestFriendsData);
            } catch (error) {
                document.getElementById('best-friends-container').innerHTML = 
                    '<div class="error">Error loading best friends: ' + error.message + '</div>';
            }
        }

        async function loadEvents() {
            try {
                const response = await fetch('/api/events');
                eventsData = await response.json();
                renderEvents(eventsData);
            } catch (error) {
                document.getElementById('events-container').innerHTML = 
                    '<div class="error">Error loading events: ' + error.message + '</div>';
            }
        }

        function renderBestFriends(friends) {
            const container = document.getElementById('best-friends-container');
            
            if (friends.length === 0) {
                container.innerHTML = '<div class="loading">No friend pairs found.</div>';
                return;
            }

            const friendsGrid = friends.slice(0, 6).map((friend, index) => {
                let rankClass = '';
                let rankBadge = '';
                
                if (index === 0) {
                    rankClass = 'gold';
                    rankBadge = '<div class="rank-badge gold">🥇</div>';
                } else if (index === 1) {
                    rankClass = 'silver';
                    rankBadge = '<div class="rank-badge silver">🥈</div>';
                } else if (index === 2) {
                    rankClass = 'bronze';
                    rankBadge = '<div class="rank-badge bronze">🥉</div>';
                }

                return `
                    <div class="friend-pair ${rankClass}">
                        ${rankBadge}
                        <div class="friend-names">${friend.person1} & ${friend.person2}</div>
                        <div class="events-count">${friend.events_together}</div>
                        <div class="events-label">events together</div>
                    </div>
                `;
            }).join('');

            container.innerHTML = `<div class="friends-grid">${friendsGrid}</div>`;
        }

        function renderEvents(events) {
            const container = document.getElementById('events-container');
            
            if (events.length === 0) {
                container.innerHTML = '<div class="loading">No events found.</div>';
                return;
            }

            container.innerHTML = events.map(event => `
                <div class="event-card">
                    <div class="event-title">${event.name}</div>
                    <div class="event-datetime">${formatDateTime(event.date_time)}</div>
                    
                    <div class="event-detail">
                        <span class="event-label">Activity:</span>
                        <span class="clickable-link activity-link" onclick="showActivityDetails('${event.activity_name}')">
                            ${event.activity_name}
                        </span>
                    </div>
                    
                    <div class="event-detail">
                        <span class="event-label">Attendees:</span>
                        <div class="person-tags">
                            ${event.people.map(person => 
                                `<span class="clickable-link person-link" onclick="showPersonDetails('${person}')">${person}</span>`
                            ).join('')}
                        </div>
                    </div>
                    
                    ${event.activity ? `
                        <div class="event-detail" style="margin-top: 1rem; font-size: 0.9rem; color: #666;">
                            <span class="event-label">Type:</span> ${event.activity.type} | 
                            <span class="event-label">Indoor:</span> ${event.activity.indoor ? 'Yes' : 'No'} | 
                            <span class="event-label">Outdoor:</span> ${event.activity.outdoor ? 'Yes' : 'No'}
                        </div>
                    ` : ''}
                </div>
            `).join('');
        }

        async function showActivityDetails(activityName) {
            const sidebar = document.getElementById('sidebar-content');
            sidebar.innerHTML = '<div class="loading">Loading activity details...</div>';

            try {
                const response = await fetch(`/api/activity/${encodeURIComponent(activityName)}/events`);
                const data = await response.json();

                sidebar.innerHTML = `
                    <div class="count-badge">${data.event_count} Events</div>
                    <h4>${data.activity_name}</h4>
                    <p style="margin-bottom: 1rem;">Events organized for this activity:</p>
                    ${data.events.map(event => `
                        <div class="sidebar-event">
                            <h4>${event.name}</h4>
                            <p>${formatDateTime(event.date_time)}</p>
                            <p>Attendees: ${event.people.join(', ')}</p>
                        </div>
                    `).join('')}
                `;
            } catch (error) {
                sidebar.innerHTML = '<div class="error">Error loading activity details: ' + error.message + '</div>';
            }
        }

        async function showPersonDetails(personName) {
            const sidebar = document.getElementById('sidebar-content');
            sidebar.innerHTML = '<div class="loading">Loading person details...</div>';

            try {
                const response = await fetch(`/api/person/${encodeURIComponent(personName)}/events`);
                const data = await response.json();

                sidebar.innerHTML = `
                    <div class="count-badge">${data.event_count} Events</div>
                    <h4>${data.person_name}</h4>
                    <p style="margin-bottom: 1rem;">Events attended by this person:</p>
                    ${data.events.map(event => `
                        <div class="sidebar-event">
                            <h4>${event.name}</h4>
                            <p>Activity: ${event.activity_name}</p>
                            <p>${formatDateTime(event.date_time)}</p>
                            <p>With: ${event.people.filter(p => p !== personName).join(', ')}</p>
                        </div>
                    `).join('')}
                `;
            } catch (error) {
                sidebar.innerHTML = '<div class="error">Error loading person details: ' + error.message + '</div>';
            }
        }

        function formatDateTime(dateTimeStr) {
            if (!dateTimeStr) return 'Date not available';
            const date = new Date(dateTimeStr);
            return date.toLocaleString('en-US', {
                weekday: 'long',
                year: 'numeric',
                month: 'long',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
        }

        async function askQuery() {
            const queryInput = document.getElementById('query-input');
            const queryButton = document.getElementById('query-button');
            const responseDiv = document.getElementById('query-response');
            
            const query = queryInput.value.trim();
            if (!query) {
                responseDiv.innerHTML = '<div class="query-answer">Please enter a question!</div>';
                responseDiv.classList.add('show');
                return;
            }

            // Disable button and show loading
            queryButton.disabled = true;
            queryButton.textContent = 'Thinking...';
            responseDiv.innerHTML = '<div class="query-answer">🤔 Let me think about that...</div>';
            responseDiv.classList.add('show');

            try {
                const response = await fetch('/api/query', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ query: query })
                });

                const data = await response.json();
                
                if (response.ok) {
                    responseDiv.innerHTML = `<div class="query-answer">💡 ${data.answer}</div>`;
                } else {
                    responseDiv.innerHTML = `<div class="query-answer" style="color: #e74c3c;">❌ Error: ${data.error}</div>`;
                }
            } catch (error) {
                responseDiv.innerHTML = `<div class="query-answer" style="color: #e74c3c;">❌ Error: ${error.message}</div>`;
            } finally {
                // Re-enable button
                queryButton.disabled = false;
                queryButton.textContent = 'Ask';
            }
        }

        // Load data when page loads
        document.addEventListener('DOMContentLoaded', function() {
            loadBestFriends();
            loadEvents();
            
            // Set up query functionality
            const queryButton = document.getElementById('query-button');
            const queryInput = document.getElementById('query-input');
            
            queryButton.addEventListener('click', askQuery);
            
            // Allow Enter key to submit query
            queryInput.addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    askQuery();
                }
            });
        });
    </script>
</body>
</html>
'''

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)