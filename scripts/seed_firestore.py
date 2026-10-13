#!/usr/bin/env python3
"""Seed Firestore with curated travel destinations and experiences for Voyage Concierge."""

from google.cloud import firestore

# CRITICAL: Hardcode project ID as string. Do not use google.auth.default() or GOOGLE_CLOUD_PROJECT.
PROJECT_ID = "qwiklabs-gcp-04-d718c29e3c1e"

SAMPLE_DESTINATIONS = [
    {
        "id": "paris-france",
        "name": "Paris",
        "country": "France",
        "region": "Europe",
        "travel_vibes": ["romance", "art", "culinary", "history", "fashion"],
        "ideal_duration_days": 4,
        "best_season": "Spring (April–June) & Autumn (September–November)",
        "highlights": [
            "Musée d'Orsay & Louvre masterpieces",
            "St-Germain-des-Prés cafe culture and artisanal bakeries",
            "Sunset Seine river cruise by Pont Neuf",
            "Montmartre bohemian alleys and Sacré-Cœur vistas",
        ],
        "neighborhoods": [
            {"name": "Le Marais", "vibe": "Historic mansions, contemporary boutiques, falafel & cafes"},
            {"name": "Saint-Germain", "vibe": "Literary cafes, art galleries, elegant boulevards"},
            {"name": "Montmartre", "vibe": "Artistic hilltop quarter with winding cobblestones"},
        ],
        "dining_scene": "Bistronomy, renowned pâtisseries, vegetarian-friendly farm-to-table spots, wine bars.",
        "passport_rule": "Schengen area rules: passport must be valid for at least 3-6 months beyond stay; 90-day visa waiver for US/EU citizens.",
        "base_budget_level": "moderate-to-luxury",
    },
    {
        "id": "kyoto-japan",
        "name": "Kyoto",
        "country": "Japan",
        "region": "Asia",
        "travel_vibes": ["culture", "tranquility", "artisan-crafts", "tea-culture", "temples"],
        "ideal_duration_days": 5,
        "best_season": "Spring (Cherry Blossoms) & Autumn (Crimson Foliage)",
        "highlights": [
            "Fushimi Inari-Taisha early morning torii gate walk",
            "Arashiyama bamboo grove and Tenryu-ji Zen garden",
            "Gion historic preserved teahouse district",
            "Kiyomizu-dera panoramic wooden stage overlooking the hillside",
        ],
        "neighborhoods": [
            {"name": "Higashiyama", "vibe": "Traditional wooden machiya houses, historic temples, artisan pottery"},
            {"name": "Arashiyama", "vibe": "River views, bamboo paths, peaceful mountain scenery"},
            {"name": "Nakagyo", "vibe": "Central Nishiki market food scene and craft shops"},
        ],
        "dining_scene": "Kaiseki seasonal dining, tofu cuisine (yudofu), soba noodles, green tea sweets, pescatarian & vegetarian friendly options.",
        "passport_rule": "6 months passport validity recommended. 90-day visa-free for tourist visits from US, Canada, UK, and EU.",
        "base_budget_level": "moderate-to-luxury",
    },
    {
        "id": "rome-italy",
        "name": "Rome",
        "country": "Italy",
        "region": "Europe",
        "travel_vibes": ["ancient-history", "architecture", "food", "walking-city"],
        "ideal_duration_days": 4,
        "best_season": "Spring (April–May) and Autumn (October–November)",
        "highlights": [
            "Colosseum and Roman Forum archaeological park",
            "Vatican Museums and Sistine Chapel frescoes",
            "Sunset at the Spanish Steps and Trevi Fountain espresso stops",
            "Trastevere evening strolls and authentic trattorias",
        ],
        "neighborhoods": [
            {"name": "Trastevere", "vibe": "Cobbled lanes, lively piazza life, authentic Roman trattorias"},
            {"name": "Monti", "vibe": "Hip neighborhood with vintage boutiques and artisan cafes near the Colosseum"},
            {"name": "Campo de' Fiori / Navona", "vibe": "Baroque fountains, morning open-air market"},
        ],
        "dining_scene": "Classic Roman pastas (cacio e pepe, carbonara), wood-fired pizza al taglio, artisanal gelato, fresh espresso bars.",
        "passport_rule": "Schengen rules: minimum 3-6 months validity past departure.",
        "base_budget_level": "moderate",
    },
    {
        "id": "chiang-mai-thailand",
        "name": "Chiang Mai",
        "country": "Thailand",
        "region": "Southeast Asia",
        "travel_vibes": ["nature", "spirituality", "cooking", "night-markets", "artisan-crafts"],
        "ideal_duration_days": 4,
        "best_season": "November to February (Cool, dry season)",
        "highlights": [
            "Wat Phra That Doi Suthep mountain temple overlooking the valley",
            "Sunday Walking Street Night Market artisan stalls and crafts",
            "Hands-on organic Thai cooking school in the countryside",
            "Ethical elephant rescue sanctuary visits",
        ],
        "neighborhoods": [
            {"name": "Old City", "vibe": "Moated ancient quarter filled with golden temples and leafy cafes"},
            {"name": "Nimman (Nimmanhaemin)", "vibe": "Trendy design district, third-wave coffee, boutique shops"},
            {"name": "Riverside (Ping River)", "vibe": "Scenic waterside dining and tranquil boutique resorts"},
        ],
        "dining_scene": "Northern Thai delicacies like Khao Soi, fresh tropical fruits, organic vegan cafes, vibrant street food.",
        "passport_rule": "Strict 6-month passport validity required. 60-day visa exemption available for many nationalities.",
        "base_budget_level": "budget-friendly",
    },
    {
        "id": "reykjavik-iceland",
        "name": "Reykjavik & Golden Circle",
        "country": "Iceland",
        "region": "Nordic / Europe",
        "travel_vibes": ["nature", "adventure", "geothermal", "northern-lights", "photography"],
        "ideal_duration_days": 5,
        "best_season": "September–March for Northern Lights; June–August for Midnight Sun & lush highlands",
        "highlights": [
            "Golden Circle (Thingvellir National Park, Geysir, Gullfoss waterfall)",
            "Soaking in Blue Lagoon or Sky Lagoon geothermal waters",
            "South Coast waterfalls (Seljalandsfoss, Skogafoss) and black sand beaches",
            "Harpa Concert Hall and colorful downtown street art",
        ],
        "neighborhoods": [
            {"name": "Miðborg (Downtown)", "vibe": "Walkable harbor front, Nordic design shops, cozy bakeries"},
            {"name": "Grandí", "vibe": "Old harbor district transformed into trendy foodie and artisan warehouse hub"},
        ],
        "dining_scene": "Fresh wild Arctic seafood, traditional rye bread, sourdough bakeries, contemporary Nordic cuisine.",
        "passport_rule": "Schengen area regulations apply (at least 3 months validity beyond departure).",
        "base_budget_level": "luxury",
    },
]


def seed_database():
    print(f"Connecting to Firestore for project: '{PROJECT_ID}'...")
    db = firestore.Client(project=PROJECT_ID)
    collection_ref = db.collection("travel_destinations")

    print(f"Seeding {len(SAMPLE_DESTINATIONS)} destinations into 'travel_destinations' collection...")
    for item in SAMPLE_DESTINATIONS:
        doc_id = item["id"]
        collection_ref.document(doc_id).set(item)
        print(f"  ✓ Seeded destination: {item['name']} ({item['country']}) -> ID: {doc_id}")

    print("\n✅ Successfully seeded Firestore 'travel_destinations' collection!")


if __name__ == "__main__":
    seed_database()
