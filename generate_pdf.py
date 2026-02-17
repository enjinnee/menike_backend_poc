"""
Generates a professional PDF document describing the Manike B2B AI Engine project workflow.
"""
from fpdf import FPDF

class ProjectPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 8, "Manike B2B AI Engine - Project Workflow", align="R")
        self.ln(4)
        self.set_draw_color(0, 120, 200)
        self.set_line_width(0.5)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(6)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def section_title(self, title):
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(0, 90, 180)
        self.cell(0, 10, title)
        self.ln(8)

    def sub_title(self, title):
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(50, 50, 50)
        self.cell(0, 8, title)
        self.ln(6)

    def body_text(self, text):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(40, 40, 40)
        self.multi_cell(0, 5.5, text)
        self.ln(3)

    def bullet(self, text, indent=10):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(40, 40, 40)
        x = self.get_x()
        self.set_x(x + indent)
        self.cell(4, 5.5, "-")
        self.multi_cell(0, 5.5, text)
        self.ln(1)

    def code_block(self, text):
        self.set_font("Courier", "", 9)
        self.set_fill_color(240, 240, 240)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 5, text, fill=True)
        self.ln(3)

    def flow_step(self, number, title, description):
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(255, 255, 255)
        self.set_fill_color(0, 120, 200)
        self.cell(8, 7, str(number), fill=True, align="C")
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(30, 30, 30)
        self.cell(0, 7, f"  {title}")
        self.ln(8)
        self.body_text(description)


def generate_pdf():
    pdf = ProjectPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)

    # =========================================================================
    # PAGE 1: Title Page
    # =========================================================================
    pdf.add_page()
    pdf.ln(40)
    pdf.set_font("Helvetica", "B", 28)
    pdf.set_text_color(0, 90, 180)
    pdf.cell(0, 15, "Manike B2B AI Engine", align="C")
    pdf.ln(12)
    pdf.set_font("Helvetica", "", 16)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 10, "Project Workflow Documentation", align="C")
    pdf.ln(10)
    pdf.set_font("Helvetica", "I", 11)
    pdf.cell(0, 8, "Multi-Tenant AI Scene Orchestrator & Itinerary Engine", align="C")
    pdf.ln(25)

    pdf.set_draw_color(0, 120, 200)
    pdf.set_line_width(0.8)
    pdf.line(60, pdf.get_y(), 150, pdf.get_y())
    pdf.ln(15)

    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 7, "Version: 2.0.0", align="C")
    pdf.ln(7)
    pdf.cell(0, 7, "Architecture: FastAPI + PostgreSQL + Milvus", align="C")
    pdf.ln(7)
    pdf.cell(0, 7, "Date: February 2026", align="C")

    # =========================================================================
    # PAGE 2: Architecture Overview
    # =========================================================================
    pdf.add_page()
    pdf.section_title("1. Architecture Overview")
    pdf.body_text(
        "The Manike B2B AI Engine is a multi-tenant backend system designed for travel companies. "
        "It uses a hybrid database architecture combining PostgreSQL for structured data and Milvus "
        "for vector-based semantic search. The system orchestrates multiple AI services to generate "
        "cinematic travel content including images, videos, and itineraries."
    )

    pdf.sub_title("Technology Stack")
    pdf.bullet("Framework: FastAPI (Python)")
    pdf.bullet("Relational DB: PostgreSQL (via SQLModel/SQLAlchemy)")
    pdf.bullet("Vector DB: Milvus (for AI-powered semantic search)")
    pdf.bullet("Authentication: JWT (JSON Web Tokens)")
    pdf.bullet("Media Processing: FFmpeg")
    pdf.bullet("Storage: S3-compatible object storage")
    pdf.bullet("AI Models: LLM (GPT-4/Claude), Image Gen, Video Gen (pluggable)")
    pdf.ln(3)

    pdf.sub_title("Project Structure")
    pdf.code_block(
        "menike_backend_poc/\n"
        "|-- app/\n"
        "|   |-- api/              # API endpoint routers\n"
        "|   |   |-- auth.py       # Login & JWT token generation\n"
        "|   |   |-- scenes.py     # Scene orchestration endpoints\n"
        "|   |   |-- itinerary.py  # Itinerary generation endpoints\n"
        "|   |   |-- experiences.py# Experience CRUD (Milvus)\n"
        "|   |   |-- tenants.py    # Tenant management (Milvus)\n"
        "|   |-- core/             # Core infrastructure\n"
        "|   |   |-- auth.py       # JWT logic & password hashing\n"
        "|   |   |-- database.py   # PostgreSQL engine & sessions\n"
        "|   |   |-- milvus_client.py # Milvus connection & queries\n"
        "|   |-- models/           # Data models\n"
        "|   |   |-- sql_models.py # Tenant, User, Scene (PostgreSQL)\n"
        "|   |   |-- milvus_schema.py # Vector collection schemas\n"
        "|   |-- services/         # Business logic\n"
        "|   |   |-- orchestrator.py  # AI scene pipeline\n"
        "|   |   |-- generators.py    # LLM, Image, Video generators\n"
        "|   |   |-- media_processor.py # FFmpeg wrapper\n"
        "|   |   |-- storage.py       # S3 file upload\n"
        "|   |-- main.py           # FastAPI app entry point\n"
        "|-- seed_db.py            # Database seeding script\n"
        "|-- requirements.txt      # Python dependencies\n"
        "|-- .env                  # Environment variables"
    )

    # =========================================================================
    # PAGE 3: Complete Working Flow
    # =========================================================================
    pdf.add_page()
    pdf.section_title("2. Complete Working Flow")
    pdf.body_text(
        "The following describes the end-to-end flow of how a request travels through the system, "
        "from user authentication to AI content generation and storage."
    )

    pdf.sub_title("Phase A: Authentication Flow")
    pdf.flow_step(1, "User Login", 
        "The client sends a POST request to /auth/login with email and password. "
        "The system verifies the credentials against the PostgreSQL 'user' table using "
        "PBKDF2_SHA256 password hashing.")
    pdf.flow_step(2, "JWT Token Generation", 
        "On successful authentication, the server generates a JWT token containing the "
        "user's ID and tenant_id. This token is valid for 24 hours and must be included "
        "in the Authorization header of all subsequent requests.")
    pdf.flow_step(3, "Tenant Extraction", 
        "Every protected endpoint uses the get_current_tenant_id dependency, which decodes "
        "the JWT token, retrieves the user from PostgreSQL, and returns their tenant_id. "
        "This ensures complete data isolation between tenants.")

    pdf.ln(5)
    pdf.sub_title("Phase B: Scene Orchestration Flow (Core AI Pipeline)")
    pdf.flow_step(4, "Scene Request", 
        "The authenticated client sends a POST request to /scenes/ with a scene name and "
        "description (e.g., 'Galle Fort Sunset' with a cinematic description).")
    pdf.flow_step(5, "Database Record Creation", 
        "The SceneOrchestrator creates a new Scene record in PostgreSQL with status='pending', "
        "linked to the authenticated tenant_id. It then updates the status to 'processing'.")
    pdf.flow_step(6, "LLM Prompt Engineering", 
        "The LLMPromptEngine analyzes the scene description and generates structured prompts:\n"
        "  - image_prompt: Optimized for photorealistic image generation\n"
        "  - video_prompt: Optimized for cinematic video generation\n"
        "  - negative_prompt: Quality guard rails for AI models")
    pdf.flow_step(7, "AI Image Generation", 
        "The ImageGenerator receives the image_prompt and produces a high-quality travel image. "
        "Currently uses a mock implementation; in production, this connects to Stable Diffusion, "
        "DALL-E, or Leonardo AI.")
    pdf.flow_step(8, "AI Video Generation", 
        "The VideoGenerator receives the video_prompt and produces a cinematic video clip. "
        "Currently uses a mock; in production, connects to Veo 3 or Runway ML.")

    pdf.add_page()
    pdf.flow_step(9, "Media Processing (FFmpeg)", 
        "The MediaProcessor uses FFmpeg to optimize the generated video:\n"
        "  - Compression for web streaming\n"
        "  - Format standardization (MP4/H.264)\n"
        "  - Resolution and bitrate optimization")
    pdf.flow_step(10, "Storage Upload", 
        "The optimized media file is uploaded to S3-compatible storage. A public URL is "
        "generated and stored back in the Scene record in PostgreSQL.")
    pdf.flow_step(11, "Completion", 
        "The Scene record is updated with status='completed', the media_url, and a timestamp. "
        "The complete scene object is returned to the client.")

    pdf.ln(5)
    pdf.sub_title("Phase C: Itinerary Generation Flow")
    pdf.flow_step(12, "Itinerary Request", 
        "The client sends a POST to /itinerary/generate with destination, number of days, "
        "and interests. The system generates a structured multi-day travel plan.")
    pdf.flow_step(13, "AI Planning", 
        "The LLM creates a logical itinerary with activities, travel times, and distances. "
        "It also generates image prompts for each activity for visual enrichment.")

    pdf.ln(5)
    pdf.sub_title("Phase D: Experience Vector Search Flow")
    pdf.flow_step(14, "Experience Storage", 
        "Travel experiences are stored in Milvus as vector embeddings (768-dimensional). "
        "Each experience is tagged with a tenant_id for data isolation.")
    pdf.flow_step(15, "Semantic Search", 
        "The client can search for similar experiences using POST /experiences/search/ "
        "with a query vector. Milvus performs HNSW-based approximate nearest neighbor search "
        "filtered by tenant_id, returning the most relevant results ranked by cosine similarity.")

    # =========================================================================
    # PAGE 5: Data Flow Diagram
    # =========================================================================
    pdf.add_page()
    pdf.section_title("3. Data Flow Diagram")
    pdf.body_text("The following illustrates how data moves through the system layers:")
    pdf.ln(3)

    # Draw a simple flow diagram using PDF primitives
    start_y = pdf.get_y()
    box_w, box_h = 55, 18
    gap = 8
    
    boxes = [
        ("Client App", (30, start_y), (0, 120, 200)),
        ("API Gateway", (30, start_y + box_h + gap), (0, 150, 100)),
        ("Auth Service", (100, start_y + box_h + gap), (200, 100, 0)),
        ("Scene Orchestrator", (30, start_y + 2*(box_h + gap)), (180, 50, 50)),
        ("LLM Engine", (100, start_y + 2*(box_h + gap)), (120, 80, 180)),
        ("Image/Video Gen", (100, start_y + 3*(box_h + gap)), (120, 80, 180)),
        ("Media Processor", (30, start_y + 3*(box_h + gap)), (100, 100, 100)),
        ("PostgreSQL", (30, start_y + 4*(box_h + gap)), (0, 90, 180)),
        ("Milvus", (100, start_y + 4*(box_h + gap)), (220, 150, 0)),
        ("S3 Storage", (170, start_y + 4*(box_h + gap)), (50, 150, 50)),
    ]

    for label, (x, y), (r, g, b) in boxes:
        pdf.set_fill_color(r, g, b)
        pdf.set_draw_color(r, g, b)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_xy(x, y)
        pdf.cell(box_w, box_h, label, fill=True, align="C", border=1)

    # Draw arrows (simple lines)
    pdf.set_draw_color(100, 100, 100)
    pdf.set_line_width(0.4)
    # Client -> API Gateway
    pdf.line(57, start_y + box_h, 57, start_y + box_h + gap)
    # API Gateway -> Auth
    pdf.line(85, start_y + box_h + gap + box_h/2, 100, start_y + box_h + gap + box_h/2)
    # API Gateway -> Orchestrator
    pdf.line(57, start_y + box_h + gap + box_h, 57, start_y + 2*(box_h + gap))
    # Orchestrator -> LLM
    pdf.line(85, start_y + 2*(box_h + gap) + box_h/2, 100, start_y + 2*(box_h + gap) + box_h/2)
    # LLM -> Image/Video
    pdf.line(127, start_y + 2*(box_h + gap) + box_h, 127, start_y + 3*(box_h + gap))
    # Orchestrator -> Media Processor
    pdf.line(57, start_y + 2*(box_h + gap) + box_h, 57, start_y + 3*(box_h + gap))
    # Media Processor -> PostgreSQL
    pdf.line(57, start_y + 3*(box_h + gap) + box_h, 57, start_y + 4*(box_h + gap))
    # Orchestrator -> Milvus
    pdf.line(127, start_y + 3*(box_h + gap) + box_h, 127, start_y + 4*(box_h + gap))
    # Media Processor -> S3
    pdf.line(85, start_y + 3*(box_h + gap) + box_h/2, 170, start_y + 4*(box_h + gap) + box_h/2)

    pdf.set_y(start_y + 5*(box_h + gap) + 5)

    # =========================================================================
    # PAGE 6: API Endpoints Summary
    # =========================================================================
    pdf.add_page()
    pdf.section_title("4. API Endpoints Summary")

    # Table header
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(0, 90, 180)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(25, 8, "Method", fill=True, border=1, align="C")
    pdf.cell(55, 8, "Endpoint", fill=True, border=1, align="C")
    pdf.cell(110, 8, "Description", fill=True, border=1, align="C")
    pdf.ln()

    endpoints = [
        ("POST", "/auth/login", "Authenticate user, returns JWT token"),
        ("POST", "/scenes/", "Create a new AI-orchestrated scene"),
        ("GET", "/scenes/", "List all scenes for the authenticated tenant"),
        ("POST", "/itinerary/generate", "Generate a multi-day travel itinerary"),
        ("GET", "/experiences/", "List all experiences from Milvus"),
        ("POST", "/experiences/", "Create a new experience in Milvus"),
        ("POST", "/experiences/search/", "Semantic vector search for experiences"),
        ("POST", "/tenants/", "Create a new tenant in Milvus"),
        ("GET", "/tenants/", "List all tenants"),
        ("GET", "/tenants/{id}", "Get a specific tenant by ID"),
        ("PUT", "/tenants/{id}", "Update a tenant"),
        ("DELETE", "/tenants/{id}", "Delete a tenant"),
    ]

    pdf.set_font("Helvetica", "", 9)
    for i, (method, endpoint, desc) in enumerate(endpoints):
        if i % 2 == 0:
            pdf.set_fill_color(245, 245, 255)
        else:
            pdf.set_fill_color(255, 255, 255)
        
        pdf.set_text_color(40, 40, 40)
        # Method with color
        if method == "POST":
            pdf.set_text_color(0, 130, 0)
        elif method == "GET":
            pdf.set_text_color(0, 90, 180)
        elif method == "PUT":
            pdf.set_text_color(200, 130, 0)
        elif method == "DELETE":
            pdf.set_text_color(200, 50, 50)
        
        pdf.cell(25, 7, method, fill=True, border=1, align="C")
        pdf.set_text_color(40, 40, 40)
        pdf.set_font("Courier", "", 8)
        pdf.cell(55, 7, endpoint, fill=True, border=1)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(110, 7, desc, fill=True, border=1)
        pdf.ln()

    pdf.ln(8)

    # =========================================================================
    # Database Models
    # =========================================================================
    pdf.section_title("5. Database Models")
    
    pdf.sub_title("PostgreSQL Tables")
    pdf.bullet("Tenant: id, name, api_key, config, created_at")
    pdf.bullet("User: id, tenant_id (FK), email, hashed_password, role, created_at")
    pdf.bullet("Scene: id, tenant_id, name, description, status, media_url, created_at, updated_at")
    
    pdf.ln(3)
    pdf.sub_title("Milvus Collections")
    pdf.bullet("experiences: id, tenant_id, embedding (768-dim), metadata (JSON), slug")
    pdf.bullet("tenants: id, name, apikey, metadata (JSON), embedding (2-dim placeholder)")

    # =========================================================================
    # PAGE 7: How to Run
    # =========================================================================
    pdf.add_page()
    pdf.section_title("6. How to Run the Project")

    pdf.sub_title("Prerequisites")
    pdf.bullet("Python 3.10+")
    pdf.bullet("Docker Desktop (for PostgreSQL and Milvus)")
    pdf.bullet("pip (Python package manager)")

    pdf.ln(3)
    pdf.sub_title("Step 1: Start Docker Services")
    pdf.code_block(
        "# Start PostgreSQL\n"
        "docker run -d --name postgres_local \\\n"
        "  -e POSTGRES_USER=admin \\\n"
        "  -e POSTGRES_PASSWORD=admin \\\n"
        "  -e POSTGRES_DB=menike \\\n"
        "  -p 5432:5432 postgres:latest\n\n"
        "# Start Milvus (using docker-compose)\n"
        "# Follow: https://milvus.io/docs/install_standalone-docker.md"
    )

    pdf.sub_title("Step 2: Configure Environment")
    pdf.code_block(
        "# .env file contents:\n"
        "DATABASE_URL=postgresql://admin:admin@localhost:5432/menike"
    )

    pdf.sub_title("Step 3: Install Dependencies & Seed")
    pdf.code_block(
        "pip install -r requirements.txt\n"
        "python seed_db.py"
    )

    pdf.sub_title("Step 4: Run the Server")
    pdf.code_block(
        "export PYTHONPATH=$PYTHONPATH:$(pwd)\n"
        "python app/main.py\n\n"
        "# Server starts at http://localhost:8000\n"
        "# Swagger UI at http://localhost:8000/docs"
    )

    pdf.sub_title("Step 5: Test the Flow via Swagger")
    pdf.body_text(
        "1. Open http://localhost:8000/docs\n"
        "2. POST /auth/login with: username=admin@manike.ai, password=admin123\n"
        "3. Copy the access_token from the response\n"
        "4. Click 'Authorize' button, paste the token\n"
        "5. POST /scenes/ to create a scene\n"
        "6. GET /scenes/ to verify the scene was created"
    )

    # =========================================================================
    # Save
    # =========================================================================
    output_path = "/Users/sudathjayakodi/Documents/POC/menike_backend_poc/Manike_B2B_AI_Engine_Workflow.pdf"
    pdf.output(output_path)
    print(f"PDF generated successfully: {output_path}")
    return output_path


if __name__ == "__main__":
    generate_pdf()
