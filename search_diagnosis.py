from Bio import Entrez
import time
import openai
import json
import os


# Function to search PubMed and retrieve top results
def search_pubmed(query, max_results=10):
    Entrez.email = "mvakde12@gmil.com"  # Replace with your email
    handle = Entrez.esearch(db="pubmed", term=query, retmax=max_results)
    record = Entrez.read(handle)
    handle.close()
    return record["IdList"]


# Function to fetch specific details for PubMed IDs
def fetch_pubmed_details(id_list, fields="abstract"):
    rettype = (
        "abstract"
        if fields == "abstract"
        else "uilist" if fields == "pmid" else "medline"
    )
    retmode = "text" if fields in ["abstract", "pmid"] else "xml"

    handle = Entrez.efetch(
        db="pubmed", id=",".join(id_list), rettype=rettype, retmode=retmode
    )
    details = handle.read()
    handle.close()
    return details


# Function to parse titles and abstracts from Medline records (if needed)
def parse_medline_records(xml_data):
    from xml.etree import ElementTree as ET

    root = ET.fromstring(xml_data)
    results = []
    for article in root.findall(".//PubmedArticle"):
        pmid_elem = article.find(".//PMID")
        pmid = pmid_elem.text if pmid_elem is not None else ""

        title_elem = article.find(".//ArticleTitle")
        title = title_elem.text if title_elem is not None else ""

        abstract_elem = article.find(".//AbstractText")
        abstract = abstract_elem.text if abstract_elem is not None else ""

        if pmid or title or abstract:
            results.append({"PMID": pmid, "Title": title, "Abstract": abstract})
        else:
            print("Skipping article with missing metadata.")

    return results


# Function to generate diagnoses using OpenAI Chat Completions API
def generate_diagnoses_with_function_call(
    system_prompt, user_prompt_1, assistant_response_1, user_prompt_2, user_prompt_3
):
    openai.api_key = os.environ["OPENAI_API_KEY"]

    def extract_keywords(diagnoses):
        """This function processes the diagnoses array."""
        return {"diagnoses": diagnoses}

    # First call to the Chat Completions API
    messages_first_call = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt_1},
        {"role": "assistant", "content": assistant_response_1},
        {"role": "user", "content": user_prompt_2},
    ]

    response_first = openai.chat.completions.create(
        model="gpt-4o-2024-11-20",  # Replace "gpt-4" with the model you are using
        messages=messages_first_call,
        max_tokens=500,
        temperature=0.7,
    )
    assistant_response = response_first.choices[0].message.content.strip()

    # Append the assistant response and user_prompt_3 for the second call
    messages_second_call = messages_first_call + [
        {"role": "assistant", "content": assistant_response},
        {"role": "user", "content": user_prompt_3},
    ]

    response = openai.chat.completions.create(
        model="gpt-4o-2024-11-20",  # Replace "gpt-4" with the model you are using
        messages=messages_second_call,
        functions=[
            {
                "name": "process_diagnoses",
                "description": "Processes and filters diagnoses",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "diagnoses": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "A list of diagnoses to process.",
                        }
                    },
                    "required": ["diagnoses"],
                },
            }
        ],
        function_call={"name": "process_diagnoses"},
    )

    # Access and parse function call arguments
    function_response = response.choices[0].message.function_call
    arguments = json.loads(function_response.arguments)
    diagnoses = arguments["diagnoses"]
    return [diag.strip() for diag in diagnoses if diag.strip()]


# Function to read the second user prompt from a markdown file
def read_user_prompt_from_file(filepath):
    with open(filepath, "r") as file:
        return file.read().strip()


# Main script
def main():
    # Generate diagnoses using OpenAI Chat Completions API
    system_prompt = "You are an expert system trained to analyze patient medical history and provide diagnostic insights. FOLLOW THE INSTRUCTIONS GIVEN EXACTLY"
    user_prompt_1 = "I am going to give you a detailed documentation about a particular patient's medical history. Create a list of keywords that you think are the most important to make a diagnosis. Understand that the patient is facing a chronic disease and therefore current doctors aren't able to diagnose him. This is because they aren't able to think outside the box. These keywords will be used to search medical literature later on for possible diagnoses"
    assistant_response_1 = "Please share the detailed documentation of the patient’s medical history. I'll analyze it to extract the most relevant and unique keywords based on symptoms, history, lab findings, and other factors. The focus will be on identifying uncommon or overlooked patterns that might be crucial for diagnosis. Once you provide the information, I'll return a comprehensive list of keywords"
    # Read second user prompt from markdown file
    user_prompt_2 = read_user_prompt_from_file("history.md")

    # Additional prompt for refinement
    user_prompt_3 = "Based on all these connections, come up with 15 diagnoses that can explain these issue. Ensure that 5 are realistic and pragmatic. While the other 10 are as out of the box as possible. You MUST make some creative connections and therefore ensure that the diagnoses are wide enough and different enough to be mutually exclusive"

    # Generate diagnoses with appended prompts
    diagnoses = generate_diagnoses_with_function_call(
        system_prompt, user_prompt_1, assistant_response_1, user_prompt_2, user_prompt_3
    )
    print(f"Relevant search parameters based on medical history: {diagnoses}")

    all_results = []

    for diagnosis in diagnoses:
        print(f"Searching PubMed for: {diagnosis}")
        try:
            # Search PubMed and fetch top 10 results
            ids = search_pubmed(diagnosis)
            if ids:
                print(f"Found {len(ids)} results for '{diagnosis}'")
                all_results.extend(ids)
            else:
                print(f"No results found for '{diagnosis}'")
        except Exception as e:
            print(f"Error during PubMed search for '{diagnosis}': {e}")

        # Pause to avoid overloading PubMed servers
        time.sleep(1)

    # Remove duplicate IDs
    unique_results = list(set(all_results))

    print(f"Total unique results: {len(unique_results)}")

    # Fetch details for all unique results based on input parameter
    field = input("Enter the field(s) to fetch (pmid/title/abstract): ").lower()
    print(f"Fetching {field} for unique results...")

    try:
        if field == "pmid":
            details = fetch_pubmed_details(unique_results, fields="pmid")
            print("PMIDs:")
            print(details)
        elif field == "title":
            xml_data = fetch_pubmed_details(unique_results, fields="medline")
            parsed_records = parse_medline_records(xml_data)
            for record in parsed_records:
                print(f"PMID: {record['PMID']}\nTitle: {record['Title']}\n")
        elif field == "abstract":
            xml_data = fetch_pubmed_details(unique_results, fields="medline")
            parsed_records = parse_medline_records(xml_data)
            for record in parsed_records:
                print(
                    f"PMID: {record['PMID']}\nTitle: {record['Title']}\nAbstract: {record['Abstract']}\n"
                )
        else:
            print("Invalid field. Please choose from 'pmid', 'title', or 'abstract'.")
    except Exception as e:
        print(f"Error fetching details: {e}")


if __name__ == "__main__":
    main()
