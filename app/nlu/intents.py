FALLBACK_INTENT = "general_chat"

# Ovvoru intent ku sample sentences. Puthu sentence vandha, edha sample ku
# romba nerukkama irukko andha intent ku poidum.
INTENT_EXAMPLES: dict[str, list[str]] = {
    "weather": [
        "what is the weather today",
        "will it rain tomorrow",
        "how hot is it in Chennai",
        "weather forecast for this weekend",
        "is it going to be sunny in Coimbatore",
        "do I need an umbrella today",
        "what's the temperature outside",
        "indha vaaram mazhai varuma",
    ],
    "set_timer": [
        "set a timer for 5 minutes",
        "start a 10 minute timer",
        "timer for 30 seconds",
        "countdown for two hours",
        "set a timer for 15 minutes for pasta",
        "cancel my timer",
        "timer vei 10 nimidam",
    ],
    "set_reminder": [
        "remind me to call mom at 6 pm",
        "set a reminder for tomorrow morning",
        "remind me to take medicine at 9",
        "don't let me forget the meeting at 3 pm",
        "add a reminder to buy milk",
        "set an alarm for 7 am",
        "wake me up at six tomorrow",
    ],
    "calculator": [
        "what is 25 times 4",
        "calculate 120 divided by 8",
        "add 45 and 67",
        "what is the square root of 144",
        "what is 15 percent of 200",
        "how much is 99 minus 37",
        "multiply 12 by 12",
    ],
    "unit_conversion": [
        "convert 5 kilometers to miles",
        "how many centimeters are in 3 inches",
        "convert 70 kilograms to pounds",
        "how many liters in a gallon",
        "what is 100 fahrenheit in celsius",
        "convert 2 hours to minutes",
        "how many feet are in a mile",
    ],
    "currency_conversion": [
        "how much is 100 dollars in rupees",
        "convert 50 euros to dollars",
        "what is the dollar rate today",
        "exchange rate for pounds to rupees",
        "convert 5000 rupees to USD",
        "how many yen is 20 dollars",
        "what is one euro in indian rupees",
    ],
    "web_search": [
        "search for best pizza recipes",
        "google the latest cricket news",
        "look up how to tie a tie online",
        "find information about electric cars",
        "search the web for python tutorials",
        "who won the match yesterday",
        "what are the latest news headlines",
        "search for the best phones under 20000",
        "look up cheap flights to Delhi",
        "find reviews of the new iPhone",
        "search online for a good gaming mouse",
        "google how to learn guitar fast",
    ],
    "play_music": [
        "play some music",
        "play Despacito on Spotify",
        "play a song by A R Rahman",
        "put on some relaxing songs",
        "pause the music",
        "skip to the next song",
        "play my workout playlist on YouTube",
        "play Vaathi Coming on YouTube",
        "play songs by Anirudh",
        "play a Tamil melody song",
        "put on an Ilaiyaraaja song",
        "play the song Why This Kolaveri Di",
    ],
    "smart_home": [
        "turn on the living room light",
        "switch off the fan",
        "set the AC to 24 degrees",
        "turn off the bedroom light",
        "lock the front door",
        "turn on the TV",
        "dim the lights",
    ],
    "time_date": [
        "what time is it",
        "what is today's date",
        "what day is it today",
        "tell me the current time",
        "what is the date tomorrow",
        "which month is it",
    ],
    "assistant_settings": [
        "speak faster",
        "talk slower",
        "increase your volume",
        "make your voice louder",
        "lower the volume",
        "speak a bit more quietly",
        "change your speaking speed",
    ],
    "greeting": [
        "hello",
        "hi there",
        "good morning",
        "hey how are you",
        "good evening",
        "vanakkam",
        "hey Nova",
    ],
    "general_chat": [
        "tell me a joke",
        "what is the capital of France",
        "explain how photosynthesis works",
        "who is Albert Einstein",
        "give me some advice on studying",
        "what do you think about artificial intelligence",
        "write a short poem about rain",
        "help me understand recursion",
    ],
}

# Ovvoru intent ku entha details (slots) extract pannanum.
# Slots illaatha intents (time_date, greeting, general_chat) ku LLM call thevai illa.
# "example" = LLM ku oru sample kaattrom (chinna model ku romba help).
INTENT_SLOTS: dict[str, dict] = {
    "weather": {
        "slots": {
            "location": "city or place name",
            "date": "day or time like today, tomorrow, this weekend",
        },
        "example": (
            "what's the weather in Chennai tomorrow",
            {"location": "Chennai", "date": "tomorrow"},
        ),
    },
    "set_timer": {
        "slots": {
            "duration": "how long, like 5 minutes or 2 hours",
            "label": "what the timer is for",
        },
        "example": (
            "set a timer for 10 minutes for pasta",
            {"duration": "10 minutes", "label": "pasta"},
        ),
    },
    "set_reminder": {
        "slots": {
            "task": "what to be reminded about",
            "time": "when, like 6 pm or tomorrow morning",
        },
        "example": (
            "remind me to call mom at 6 pm",
            {"task": "call mom", "time": "6 pm"},
        ),
    },
    "calculator": {
        "slots": {
            "expression": "the math expression using symbols like 25 * 4",
        },
        "example": (
            "what is 25 times 4",
            {"expression": "25 * 4"},
        ),
    },
    "unit_conversion": {
        "slots": {
            "value": "the number to convert",
            "from_unit": "the unit to convert from",
            "to_unit": "the unit to convert to",
        },
        "example": (
            "convert 5 kilometers to miles",
            {"value": "5", "from_unit": "kilometers", "to_unit": "miles"},
        ),
    },
    "currency_conversion": {
        "slots": {
            "amount": "the number to convert",
            "from_currency": "currency code to convert from, like USD",
            "to_currency": "currency code to convert to, like INR",
        },
        "example": (
            "how much is 100 dollars in rupees",
            {"amount": "100", "from_currency": "USD", "to_currency": "INR"},
        ),
    },
    "web_search": {
        "slots": {
            "query": "what to search for",
        },
        "example": (
            "search for best pizza recipes",
            {"query": "best pizza recipes"},
        ),
    },
    "play_music": {
        "slots": {
            "song_or_artist": "song name, artist name or playlist",
            "platform": "Spotify, YouTube, etc",
            "action": "play, pause, skip, or resume",
        },
        "example": (
            "play Despacito on Spotify",
            {"song_or_artist": "Despacito", "platform": "Spotify", "action": "play"},
        ),
    },
    "smart_home": {
        "slots": {
            "device": "light, fan, AC, TV, door lock, etc",
            "action": "on, off, lock, unlock, dim, or a value like 24 degrees",
            "room": "room name",
        },
        "example": (
            "turn off the bedroom light",
            {"device": "light", "action": "off", "room": "bedroom"},
        ),
    },
    "assistant_settings": {
        "slots": {
            "setting": "speech speed or volume",
            "change": "increase or decrease",
        },
        "example": (
            "speak faster",
            {"setting": "speech speed", "change": "increase"},
        ),
    },
}