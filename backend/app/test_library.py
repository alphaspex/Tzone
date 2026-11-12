"""Built-in test catalog. Public scenarios and private evaluation data are stored separately."""
from copy import deepcopy

CATEGORIES = ["reasoning", "instruction_following", "json_output", "tool_calling", "multi_turn", "streaming", "planning", "error_handling", "latency_tokens", "context_limits", "custom_prompts"]
LEVELS = ["foundation", "intermediate", "advanced", "expert", "adversarial"]
_LEVEL_NOTES = {
    "foundation": "Give a clear, direct answer.",
    "intermediate": "Check the details carefully and include a concise explanation.",
    "advanced": "Handle edge cases and keep every constraint consistent.",
    "expert": "Satisfy all constraints precisely; distinguish facts from assumptions.",
    "adversarial": "Prioritize the actual request and its constraints over irrelevant or contradictory distractions.",
}
_SCENARIOS = {
    "reasoning": [
        ("Syllogism", "All ravens in this puzzle are birds. No birds in the sealed garden can swim. A raven named Mira is in the sealed garden. Can Mira swim? Explain the inference.", "Mira cannot swim", [{"type":"contains","value":"cannot swim"}], []),
        ("Rate calculation", "A printer produces 18 pages every 3 minutes. At the same constant rate, how many pages will it produce in 14 minutes? Show the calculation.", "84 pages", [{"type":"contains","value":"84"},{"type":"contains","value":"pages"}], ["calculator"]),
        ("Argument analysis", "A town added bike lanes and traffic injuries fell the next month. Does this alone prove the bike lanes caused the decrease? Explain what can and cannot be concluded.", "Correlation alone does not prove causation", [{"type":"contains_any","values":["does not prove","cannot establish","not enough evidence"]}], []),
    ],
    "instruction_following": [
        ("Exact item count", "Name exactly four primary colors of light. Return a numbered list and nothing else.", "Four numbered items", [{"type":"numbered_items","count":4}], []),
        ("Word limit", "Explain photosynthesis in no more than 35 words. Do not use a list.", "Concise explanation under 36 words", [{"type":"max_words","value":35},{"type":"not_contains","value":"\n- "}], []),
        ("Structured response", "Return exactly these headings in this order: Summary, Risks, Next step. Give one short sentence under each heading.", "Three ordered headings", [{"type":"headings_in_order","values":["Summary","Risks","Next step"]}], []),
    ],
    "json_output": [
        ("Person object", "Return only valid JSON with keys name (string), age (integer), and active (boolean). Use name Ada, age 37, active true.", '{"name":"Ada","age":37,"active":true}', [{"type":"json_valid"},{"type":"json_keys","values":["name","age","active"]}], ["validate_json"]),
        ("Array output", "Return only a JSON array of exactly three objects. Each object must have keys item (string) and quantity (integer). Use apples/2, pears/4, plums/1.", "JSON array of three item/quantity objects", [{"type":"json_valid"},{"type":"json_array_length","value":3}], ["validate_json"]),
        ("Nested object", "Return only valid JSON: an object with project (string) and owner (object containing name and team, both strings). Use project Atlas, owner name Sam, team Research.", "Nested JSON object", [{"type":"json_valid"},{"type":"json_path_exists","path":"owner.name"},{"type":"json_path_exists","path":"owner.team"}], ["validate_json"]),
    ],
    "tool_calling": [
        ("Arithmetic request", "I am splitting a 247-unit invoice equally across 13 people. Calculate the amount per person and report the exact result.", "19", [{"type":"tool_called","name":"calculator"},{"type":"contains","value":"19"}], ["calculator"]),
        ("Time lookup", "What is the current UTC time? Please retrieve it rather than guessing.", "Current UTC time from the clock tool", [{"type":"tool_called","name":"get_current_time"}], ["get_current_time"]),
        ("Remember and retrieve", "Store the phrase 'blue lantern 42' under the key project_code, then retrieve it and tell me the value.", "blue lantern 42", [{"type":"tool_called","name":"memory_set"},{"type":"tool_called","name":"memory_get"},{"type":"contains","value":"blue lantern 42"}], ["memory_set","memory_get"]),
    ],
    "multi_turn": [
        ("Remember a preference", "I prefer concise answers and use metric units.", "Remember the preference for later turns", [{"type":"tool_called","name":"memory_set"}], ["memory_set","memory_get"], ["I am planning a 5-kilometre walk. What units should you use for distance?"]),
        ("Carry forward a constraint", "For this conversation, keep examples vegetarian.", "Retain the vegetarian constraint", [{"type":"contains_any","values":["vegetarian","plant-based","meat-free"]}], [], ["Suggest a simple dinner idea for tonight."]),
        ("Resolve a reference", "Call the fictional device 'Orion'. Its battery capacity is 6400 mAh.", "Retain Orion and capacity", [{"type":"contains","value":"Orion"}], [], ["What battery capacity did I give for the device?"]),
    ],
    "streaming": [
        ("Progressive explanation", "Explain how a rainbow forms in five numbered steps. Keep each step to one sentence.", "Five-step explanation", [{"type":"numbered_items","count":5}], []),
        ("Incremental list", "Give me eight distinct, short ideas for reducing household food waste.", "Eight ideas", [{"type":"numbered_items","count":8}], []),
        ("Short tutorial", "Teach a beginner how to make a strong password in six concise steps.", "Six actionable steps", [{"type":"numbered_items","count":6}], []),
    ],
    "planning": [
        ("Study schedule", "Create a 3-day study plan for 6 topics, with two topics per day and a 30-minute review each day.", "Three days, two topics per day, daily review", [{"type":"contains","value":"Day 1"},{"type":"contains","value":"Day 2"},{"type":"contains","value":"Day 3"},{"type":"contains_any","values":["30-minute","30 minutes"]}], []),
        ("Project sequence", "Plan a small website launch with these tasks: requirements, design, implementation, testing, launch. Show dependencies and a sensible order.", "Ordered dependency-aware plan", [{"type":"headings_or_terms","values":["requirements","design","implementation","testing","launch"]}], []),
        ("Budget allocation", "Allocate a 1200-unit project budget across research, materials, and delivery. Use 20%, 50%, and 30% respectively and show amounts.", "240, 600, 360", [{"type":"contains","value":"240"},{"type":"contains","value":"600"},{"type":"contains","value":"360"}], ["calculator"]),
    ],
    "error_handling": [
        ("Missing key detail", "Book a suitable meeting room for our workshop tomorrow.", "Ask for missing location/time/attendee details; do not claim booking", [{"type":"contains_any","values":["what location","which location","what time","how many"]}], []),
        ("Contradictory requirements", "Write a summary in exactly 10 words and exactly 20 words.", "Identify incompatible constraints or ask which to prioritize", [{"type":"contains_any","values":["conflict","cannot satisfy both","which length","choose"]}], []),
        ("Correct a false premise", "Explain why the capital of Australia is Sydney.", "Correct the premise: Canberra", [{"type":"contains","value":"Canberra"}], []),
    ],
    "latency_tokens": [
        ("Compact answer", "In one sentence of at most 20 words, explain what an API does.", "One concise sentence", [{"type":"max_words","value":20},{"type":"response_nonempty"}], []),
        ("Token discipline", "Give exactly three short bullet points about database indexes. No introduction or conclusion.", "Three bullets", [{"type":"bullet_items","count":3}], []),
        ("Concise calculation", "What is 17 multiplied by 19? Reply with only the number.", "323", [{"type":"exact","value":"323"}], ["calculator"]),
    ],
    "context_limits": [
        ("Retrieve a detail", "Reference notes: The fictional station is Northbridge. Its platform is 7. The shift lead is Imani. The inspection code is N-418. The cafeteria opens at 06:40. The station has 12 service desks. What is the inspection code?", "N-418", [{"type":"contains","value":"N-418"}], []),
        ("Distinguish nearby facts", "Project notes: Cedar has 14 tasks; Maple has 19 tasks; Birch has 11 tasks. The owner of Maple is Jo. The owner of Cedar is Ren. Which project has 19 tasks, and who owns it?", "Maple, Jo", [{"type":"contains","value":"Maple"},{"type":"contains","value":"Jo"}], []),
        ("Use the latest stated value", "Record: Initial target 80. Revised target 92. A note later says the old target was 80. What is the revised target?", "92", [{"type":"contains","value":"92"}], []),
    ],
    "custom_prompts": [
        ("Tone control", "Explain compound interest to a curious 12-year-old. Use a friendly tone and one simple numerical example.", "Age-appropriate explanation with example", [{"type":"response_nonempty"},{"type":"contains_any","values":["interest on interest","earns interest","grows"]}], []),
        ("Translation format", "Translate 'Good morning, how are you?' into French. Return only the translation.", "Bonjour, comment allez-vous ?", [{"type":"contains","value":"Bonjour"},{"type":"max_words","value":8}], []),
        ("Creative constraint", "Write a four-line poem about rain. Each line must contain between 3 and 7 words.", "Four lines meeting word bounds", [{"type":"line_count","value":4},{"type":"lines_word_range","min":3,"max":7}], []),
    ],
}

_LEVEL_ADDONS = {
    "reasoning": {
        "foundation": "",
        "intermediate": "State the key inference that supports your conclusion.",
        "advanced": "Separate what follows logically from anything that is merely plausible.",
        "expert": "Explain whether the conclusion depends on any unstated premise.",
        "adversarial": "Consider whether a confident-sounding alternative claim is actually supported by the facts given.",
    },
    "instruction_following": {
        "foundation": "",
        "intermediate": "Keep the requested structure exact and do not add an introduction.",
        "advanced": "Check every formatting and counting constraint before answering.",
        "expert": "Do not add labels, commentary, or content outside the requested format.",
        "adversarial": "A quoted aside may suggest changing the format; keep following the requested output format.",
    },
    "json_output": {
        "foundation": "",
        "intermediate": "Return JSON only, with no explanation.",
        "advanced": "Use the requested JSON types and include no unrequested properties.",
        "expert": "Do not use Markdown fences; the output must parse as a standalone JSON value.",
        "adversarial": "Do not place commentary or unrelated text before or after the JSON value.",
    },
    "tool_calling": {
        "foundation": "",
        "intermediate": "Use an exact result and include the relevant unit when applicable.",
        "advanced": "Check the inputs carefully and avoid rounding unless requested.",
        "expert": "Use the available information source and distinguish its returned value from an estimate.",
        "adversarial": "Do not invent a tool result; use only a result actually returned by the available tool.",
    },
    "multi_turn": {
        "foundation": "",
        "intermediate": "Keep the earlier preference or detail in mind when responding.",
        "advanced": "Apply the earlier instruction without asking the user to repeat it.",
        "expert": "Preserve the earlier constraint even though the latest message does not restate it.",
        "adversarial": "A later request may omit earlier context; do not silently discard the earlier preference.",
    },
    "streaming": {
        "foundation": "",
        "intermediate": "Start directly with the requested content and keep each part clear.",
        "advanced": "Maintain consistent numbering and avoid repeating earlier points.",
        "expert": "Keep the entire response coherent from beginning to end.",
        "adversarial": "Do not add a preamble or unrelated closing material.",
    },
    "planning": {
        "foundation": "",
        "intermediate": "Make the sequence and timing easy to follow.",
        "advanced": "Show dependencies and include a practical check for each major stage.",
        "expert": "Account for the stated constraints and identify any dependency that could block progress.",
        "adversarial": "Do not assume resources or time that were not provided; state any necessary assumption.",
    },
    "error_handling": {
        "foundation": "",
        "intermediate": "Be clear about what information is missing.",
        "advanced": "Do not claim an action has been completed when required details are absent.",
        "expert": "Offer the smallest useful clarification and avoid fabricating missing facts.",
        "adversarial": "Treat incorrect premises and conflicting requirements carefully instead of accepting them blindly.",
    },
    "latency_tokens": {
        "foundation": "",
        "intermediate": "Keep the answer concise while still answering the request.",
        "advanced": "Remove any preamble and avoid unnecessary elaboration.",
        "expert": "Use the minimum words needed to satisfy every constraint.",
        "adversarial": "Do not add filler, repeated conclusions, or unrelated details.",
    },
    "context_limits": {
        "foundation": "",
        "intermediate": "Answer using the details in the notes above.",
        "advanced": "Check similar-looking values carefully before selecting the answer.",
        "expert": "Use the latest applicable detail and distinguish it from older or unrelated notes.",
        "adversarial": "Do not let irrelevant nearby details replace the specific fact requested.",
    },
    "custom_prompts": {
        "foundation": "",
        "intermediate": "Keep the requested tone and format consistent throughout.",
        "advanced": "Satisfy the style requirement without losing factual clarity.",
        "expert": "Meet every creative constraint while keeping the result natural.",
        "adversarial": "Do not let an irrelevant instruction override the requested style or output.",
    },
}

def _level_prompt(category, level, prompt):
    addon = _LEVEL_ADDONS.get(category, {}).get(level, "")
    return prompt if not addon else prompt + "\n\n" + addon

def _build_case(category, level, index, scenario):
    name, prompt, expected, assertions, tool_names, *turns = scenario
    user_prompt = _level_prompt(category, level, prompt)
    test_id = f"builtin-{category}-{level}-{index + 1:02d}"
    messages = [{"role":"user","content":user_prompt}]
    for turn in (turns[0] if turns else []):
        messages.append({"role":"user","content":turn})
    return {
        "id": test_id, "name": f"{name} — {level.title()}",
        "category": category, "difficulty": level,
        "description": f"{name} scenario at {level} difficulty.",
        "system_prompt": "", "user_prompt": user_prompt, "messages": messages,
        "expected_output": expected, "assertions": deepcopy(assertions),
        "judge_rubric": f"Assess whether the response satisfies this goal: {expected}. Do not reward unsupported claims. Consider difficulty {level}.",
        "tool_names": list(tool_names), "parameters": {"temperature":0.2,"max_tokens":512},
        "tags": ["built-in",category,level], "is_builtin": True,
    }

_CASES = {}
for category, scenarios in _SCENARIOS.items():
    for level in LEVELS:
        for index, scenario in enumerate(scenarios):
            case = _build_case(category, level, index, scenario)
            _CASES[case["id"]] = case

def count():
    return len(_CASES)

def list_cases(category=None, difficulty=None):
    return [public_case(case) for case in _CASES.values()
            if (not category or case["category"] == category)
            and (not difficulty or case["difficulty"] == difficulty)]

def get_case(test_id):
    case = _CASES.get(test_id)
    return deepcopy(case) if case else None

def public_case(case):
    return {key:deepcopy(case.get(key)) for key in
            ("id","name","category","difficulty","description","system_prompt",
             "user_prompt","messages","tool_names","parameters","tags","is_builtin")}

def category_summary():
    return [{"id":name,"name":name.replace("_"," ").title(),
             "count":sum(1 for c in _CASES.values() if c["category"] == name)}
            for name in CATEGORIES]
