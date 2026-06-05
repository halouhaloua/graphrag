# Auto-generated from base_config.yaml. Do not edit manually.
# Run scripts/generate_prompts.py to regenerate.

prompts = {
        # 图构建提示词，非演化模式
        "construction_general": """You are an expert information extractor and structured data organizer. 
    Your task is to analyze the provided text and extract as many valuable entities, their attributes, 
    and relations as possible in a structured JSON format.  
    Guidelines:
    1. Prioritize the following predefined schema for extraction;  
    ```{schema}```
    2. Flexibility: If the context does not fit the predefined schema, extract the valuable knowledge as needed;
    3. Conciseness: The Attributes and Triples you extract should be complementary and no semantic redundancy.
    4. Do NOT miss any useful information in the context;
    5. Quality constraints for triples:
     - Do NOT extract meaningless single symbols, punctuation marks, standalone numbers, or pure stopwords (e.g., "a", "the", "it", "this") as entities or relations.
     - Every entity mention and relation phrase must carry concrete semantic meaning within the context.
     - Avoid extracting triples where either entity is an empty string, a single character, or a meaningless placeholder.
     - If a numeric value is an important attribute (e.g., "65%", "2013-2022"), treat it as an attribute value, not as a separate entity.

    Output Format: Return only JSON as **Example Output** with:    
     - Attributes: Map each entity to its descriptive features.    
     - Triples: List relations between entities in `[entity_mention1, relation, entity_mention2]` format.  
     - Entity_types: Map each entity to its schema type based on the provided schema.
    - Macro_tags: You need to **globally, abstractly, and highly summarize** the entire text block,
      extracting high-level summarizing keywords that can represent its **overall theme, core intent, 
      and central idea**. If the keywords cannot reflect the whole, expand them into very short sentences.
      Extract an appropriate number of keywords that best represent the whole.
      - intent: **Analyze and infer** the author's specific purpose or goal in writing this paragraph.
        Do NOT use generic verbs alone (e.g., "to compare", "to argue", "to define").
        Instead, embed the concrete subject matter to form a short phrase.
        Examples (adapt to the actual chunk):
         - "compare the original novella and its film adaptation"
         - "illustrate how a director interprets a literary work"
         - "contrast the narrative structure of two versions"
        
      - topic: Reflect the **overall meaning of the whole paragraph**; 
        Do not use scattered details, do not change the original meaning, add information, or omit the core message.
        Should be some short noun phrase or keywords. Example: "Shawshank Redemption adaptation process".
        
      - function: **Analyze and infer** the paragraph's rhetorical or logical function within the broader context.
        You must derive a short, concrete phrase that describes what the paragraph **does** in context.
        Examples (adapt to the actual chunk):
         - "exemplify the relationship between source material and derivative work"
         - "provide a concrete case of film adaptation"
         - "state a factual relation of adaptation"
        Do **not** use generic labels like "definition", "example", "comparison" alone; instead, embed the topic.
        The function must be **specific to the chunk**.
     ```
     input chunk:
     {chunk}
     ```
    Example Output(Use the same language as chunk):{{
        "attributes": {{
            "Stephen King": ["profession: author"],
            "Shawshank Redemption": ["type: movie"],
            "Rita Hayworth and Shawshank Redemption": ["type: novella"],
            "Frank Darabont": ["profession: director"]
            }},
        "triples": [
            ["Shawshank Redemption", "based on", "Rita Hayworth and Shawshank Redemption"],
            ["Shawshank Redemption", "directed by", "Frank Darabont"]
        ],
        "entity_types": {{
            "Stephen King": "person",
            "Shawshank Redemption": "creative_work",
            "Rita Hayworth and Shawshank Redemption": "creative_work",
            "Frank Darabont": "person"
            }}
        "macro_tags": {{
            "intent": "compare novella with film, illustrate adaptation process",
            "topic": "Shawshank Redemption, novella-to-film adaptation",
            "function": "exemplify literary adaptation, give concrete case"
            }},
        }}""",
        # 图构建提示词，演化模式
        "construction_general_agent": """You are an expert information extractor and structured data organizer. 
    Your task is to analyze the provided text and extract as many valuable entities,
    their attributes, and relations as possible in a structured JSON format.

    Guidelines:
    1. Prioritize the following predefined schema for extraction; 
    ```{schema}```
    2. Flexibility: If the context does not fit the predefined schema, extract the valuable knowledge as needed;
    3. Conciseness: The Attributes and Triples you extract should be complementary and no semantic redundancy.
    4. Do NOT miss any useful information in the context;
    5. Quality constraints for triples:
     - Do NOT extract meaningless single symbols, punctuation marks, standalone numbers, or pure stopwords (e.g., "a", "the", "it", "this") as entities or relations.
     - Every entity mention and relation phrase must carry concrete semantic meaning within the context.
     - Avoid extracting triples where either entity is an empty string, a single character, or a meaningless placeholder.
     - If a numeric value is an important attribute (e.g., "65%", "2013-2022"), treat it as an attribute value, not as a separate entity.

    Output Format: Return only JSON as **Example Output** with:
    - Attributes: Map each entity to its descriptive features.
    - Triples: List relations between entities in `[entity_mention1, relation, entity_mention2]` format.
    - Entity_types: Map each entity to its schema type based on the provided schema.
    - Macro_tags: You need to **globally, abstractly, and highly summarize** the entire text block,
      extracting high-level summarizing keywords that can represent its **overall theme, core intent, 
      and central idea**. If the keywords cannot reflect the whole, expand them into very short sentences.
      Extract an appropriate number of keywords that best represent the whole.
      - intent: **Analyze and infer** the author's specific purpose or goal in writing this paragraph.
        Do NOT use generic verbs alone (e.g., "to compare", "to argue", "to define").
        Instead, embed the concrete subject matter to form a short phrase.
        Examples (adapt to the actual chunk):
         - "compare the original novella and its film adaptation"
         - "illustrate how a director interprets a literary work"
         - "contrast the narrative structure of two versions"
        
      - topic: Reflect the **overall meaning of the whole paragraph**; 
        Do not use scattered details, do not change the original meaning, add information, or omit the core message.
        Should be some short noun phrase or keywords. Example: "Shawshank Redemption adaptation process".
        
      - function: **Analyze and infer** the paragraph's rhetorical or logical function within the broader context.
        You must derive a short, concrete phrase that describes what the paragraph **does** in context.
        Examples (adapt to the actual chunk):
         - "exemplify the relationship between source material and derivative work"
         - "provide a concrete case of film adaptation"
         - "state a factual relation of adaptation"
        Do **not** use generic labels like "definition", "example", "comparison" alone; instead, embed the topic.
        The function must be **specific to the chunk**.

    Schema Evolution: If you find new and important entity types, relation types,
    or attribute types that are valuable for knowledge extraction,
    include them in a "new_schema_types" field. Notably,
    only when the new type is clearly distinct from all existing types and of high importance.
     ```
     input chunk:
     {chunk}
     ```
    Example Output(Return ONLY the JSON object. No other text.Use the same language as chunk):{{
        "attributes": {{
            "Stephen King": ["profession: author"],
            "Shawshank Redemption": ["type: movie"],
            "Rita Hayworth and Shawshank Redemption": ["type: novella"],
            "Frank Darabont": ["profession: director"]
            }},
        "triples":[
            ["Shawshank Redemption", "based on", "Rita Hayworth and Shawshank Redemption"],
            ["Shawshank Redemption", "directed by", "Frank Darabont"]
            ],
        "entity_types": {{
            "Stephen King": "person",
            "Shawshank Redemption": "creative_work",
            "Rita Hayworth and Shawshank Redemption": "creative_work",
            "Frank Darabont": "person"
            }},
        "macro_tags": {{
            "intent": "compare novella with film, illustrate adaptation process",
            "topic": "Shawshank Redemption, novella-to-film adaptation",
            "function": "exemplify literary adaptation, give concrete case"
            }},
        "new_schema_types": {{
            "nodes": ["Novella"],
            "relations": ["adapted_into"],
            "attributes": ["publication_year"]
            }}
        }}""",
        # 问题分解提示词
        "decomposition_general": """You are a professional question decomposition expert specializing in multi-hop reasoning.
    Given the following ontology and the question, decompose the complex question into 2-3 focused sub-questions and identify involved schema types.
    CRITICAL REQUIREMENTS:1. Each sub-question must be:  
    - Specific and focused on a single fact or relationship by identifing all entities, relationships, and reasoning steps needed  
    - Answerable independently with the given ontology  - Explicitly reference entities and relations from the original question  
    - Designed to retrieve relevant knowledge for the final answer2. For simple questions (1-2 hop), return the original question as a single sub-question3. Analyze the question and identify all schema types that might be involved4. Only return a concise JSON object with sub_questions array and involved_types object.
    Ontology:{ontology}
    Question: {question}
    Example for complex question:Original: "Which film has the director died earlier, Ethnic Notions or Gordon Of Ghost City?
    "Output:{{
    "sub_questions": [
            {{"sub-question": "Who is the director of Ethnic Notions?"}},
            {{"sub-question": "Who is the director of Gordon Of Ghost City?"}},
            {{"sub-question": "When did the director of Ethnic Notions die?"}},
            {{"sub-question": "When did the director of Gordon Of Ghost City die?"}}
            ], 
    "involved_types":{{
            "nodes": ["creative_work", "person"],
            "relations": ["directed_by"],"attributes": ["name", "date"]
            }}
        }}
    Example for simple question:Original: "What is the capital of France?
    "Output:{{
    "sub_questions":
            [
            {{"sub-question": "What is the capital of France?"}}
            ],
    "involved_types": {{
            "nodes": ["location"],
            "relations": ["located_in"],
            "attributes": ["name"]
            }}
        }}""",
        # 问题回答提示词
        "retrieval_general": '''You are an expert knowledge assistant.
    Your task is to answer the question based on the provided knowledge context.
      1. Use ONLY the information from the provided knowledge context and try your best to answer the question.
      2. If the knowledge is insufficient, reject to answer the question.
      3. Be precise and concise in your answer.
      4. For factual questions, provide the specific fact or entity name.
      5. For temporal questions, provide the specific date, year, or time.
    periodQuestion: {question}
    Knowledge Context:{context}
    Answer(be specific and direct):''',
        # 问题迭代回复提示词
        "retrieval_ircot": '''You are an expert knowledge assistant using iterative retrieval with chain-of-thought reasoning.
    Think step by step about if additional information you need to answer the question completely and accurately.
    Instructions:
      1. Analyze the current knowledge context and the question.
      2. Think about what information might be missing or unclear.
      3. If you have enough information to answer, in the end of your response, write "So the answer is:" followed by your final answer.
      4. If you need more information, in the end of your response, write a specific query begin with "The new query is:" to retrieve additional relevant information.
      5. Be specific and focused in your reasoning.
    Current Question: {current_query}
    Available Knowledge Context:{context}
    Previous Thoughts: {previous_thoughts}
    Step {step}: 
    Your reasoning:''',
}
