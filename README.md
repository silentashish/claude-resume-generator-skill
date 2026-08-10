
I want to update the skills to do the following works in the loop, update the skills to achieve this

#### Before we begin

This need to be provided my the user
- Job description (This could be pasted job descripiton or the link to the job)

#### User One time setup

- working directory provided
- master cv in the markdown format inside this repo
- master cover letter info in the markdown format for this repo

#### Packages need to be in user system 

- Latex library which should be able to 
- Text extraction from the pdf PyMuPDF

### What agent need to setup one time

- latex template for cv
- latex template for cover letter


## Step-by-Step Workflow Breakdown


**1. Analyze the job description**
you should fetch the job description from the link or pasted information from the user and extract the required technical skills and preferred technical skills and other requirement


**2. Run rag agents and gap analysis**
extract the information from the user master profile and generate the gap which are missing in the original profile vs the user profile. Once you find out what are missing, generate the context aware relevant information based on the past work experience and projects to make it align. You can also fetch the company information and their projects and stored it in the knowledge base to use as a reference for the gap analysis. For example, if job want the working with the 3D rendering and you see that houzz have project that is done in 3D, add those information in the resume stating working in that project and using those tech stac as a gap information

**3. Human Verification**
 The system pauses and presents the proposed gap-fillers. End user review, edit, or approve the specific experiences the agent selected before anything is generated.


**4. Bounded JSON Generation**

* Once verified, the LLM maps the approved data into a strict JSON schema.
* **Design Guardrails:** The schema explicitly enforces design constraints (e.g., maximum of 4 bullets per role, maximum 120 characters per bullet) so the resulting PDF never overflows onto a second page unexpectedly.
* create the pydantic schema so that the json generated will always match with the structure expected in the latex format

**5. LaTeX Sanitization (The Critical Link)**

* The raw JSON is passed through a dedicated script (e.g., in Python) designed exclusively to find and escape special LaTeX characters.
* It automatically converts characters like `%` to `\%`, `&` to `\&`, and `$` to `\$` so the compiler does not crash when dealing with company names, financial metrics, or technical symbols.

**6. Injection & Compilation**

* The sanitized JSON values are mapped directly into your pre-built, ATS-friendly LaTeX template.
* The system compiles the `.tex` file into a PDF.

**5. Post-Compilation ATS Verification Loop**

* The system takes the newly minted PDF and uses a library like PyMuPDF or pdf2text to strip the document down to its raw text string.
* The **ATS Parsing Agent** reads this raw text to verify that the section headers are intact, the chronological order is correct, and no hidden columns merged your text incorrectly.
* If the text extraction fails or scrambles the data, the agent kicks the workflow back to the JSON generation step to adjust the layout structure.

**6. Visual verification step**
In this step, you need to verify that CV looks visually correct, dates should always be in the right most side, there should be no unwated space left, text alignments and CV is 2 pages full. if there is any error, go back to the previous step and fix json formatting or update the latex template

**7. Parallel Cover Letter Track**

* A secondary agent researches the target company to extract their current values and engineering culture.
* A **Tone Calibration Agent** synthesizes this research with your master cover letter framework. It strictly enforces a highly technical, concise tone focused on engineering impact, avoiding generic marketing fluff.
* This output is mapped to a Cover Letter JSON, sent through the exact same LaTeX sanitization process, and compiled into a companion PDF.
