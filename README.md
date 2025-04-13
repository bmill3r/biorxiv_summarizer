# Using Custom Prompts with BioRxiv Paper Summarizer

The enhanced BioRxiv Paper Summarizer now supports custom prompts, allowing you to tailor the summaries to your specific needs. This guide explains how to use custom prompts effectively.

## Custom Prompt Options

You have two ways to provide a custom prompt:

1. **File-based prompt**: Save your prompt in a text file and provide the path
2. **Command-line prompt**: Provide the prompt directly as a command-line argument

## Using File-Based Custom Prompts

1. Save the prompt template (like the one included in `scientific_paper_prompt.md`) to a file
2. Run the script with the `--custom_prompt` option:

```bash
python biorxiv_summarizer.py --topic "CRISPR" --max_papers 3 --custom_prompt "scientific_paper_prompt.md"
```

This is the recommended approach for complex prompts as it keeps your command line clean and makes the prompt reusable.

## Using Command-Line Prompts

For simpler prompts or one-off analyses, you can provide the prompt directly:

```bash
python biorxiv_summarizer.py --topic "genomics" --max_papers 2 --prompt_string "Analyze the paper {title} by {authors}. Focus on methodological strengths and weaknesses."
```

## Available Placeholders

Your custom prompt can include these placeholders that will be replaced with actual paper data:

- `{title}`: The paper's title
- `{authors}`: Comma-separated list of authors
- `{abstract}`: The paper's abstract
- `{doi}`: The paper's DOI
- `{date}`: The publication date
- `{paper_text}`: The extracted text from the paper (limited to first ~10,000 characters)

## Example Use Cases

### 1. Focused Methodological Assessment

```
Please analyze the methodology of paper "{title}" by {authors}.

- What methods did they use?
- Are the methods appropriate for the research question?
- What are the strengths and weaknesses of the chosen approach?
- What alternative methods could have been used?

Paper text:
{paper_text}
```

### 2. Educational Summary for Students

```
Create a pedagogical summary of "{title}" for undergraduate students.

Abstract: {abstract}

Paper content: {paper_text}

Your summary should:
1. Explain the key concepts in simple terms
2. Highlight the significance of the findings
3. Explain any technical terms
4. Connect the research to foundational concepts in biology
5. Suggest 3 discussion questions for a classroom setting
```

### 3. Research Replication Assessment

```
Assess the replicability of the study "{title}" (DOI: {doi}) published on {date}.

Paper content: {paper_text}

Please analyze:
1. Are the methods described in sufficient detail to replicate?
2. Are all materials, data, and code accessible?
3. What potential barriers exist to replication?
4. Rate the overall replicability on a scale of 1-5, with justification
5. Suggest specific steps to improve replicability
```

### 4. Cross-Paper Thematic Analysis

This prompt works well when you're processing multiple papers on the same topic:

```
Analyze paper "{title}" by {authors} as part of a thematic review of [YOUR TOPIC].

Paper content
