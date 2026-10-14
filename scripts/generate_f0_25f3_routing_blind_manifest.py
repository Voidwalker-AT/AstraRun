"""Generator and freezer for F0-25F.3 Stage 6 Routing Blind Holdout Manifest.

Constructs an authoritative, balanced blind holdout of 220 prompts (55 per class)
specifically designed to evaluate both recall and precision, including difficult
lexical collisions (prompts with 'code', 'plot', 'solve', 'log', 'bar', 'table',
'python', 'report', 'summary', 'count' that are NOT dynamic execution).

Generates: docs/audit/F0_25F3_ROUTING_BLIND_MANIFEST.json
"""

import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# 1. Dynamic Computation (55 prompts): genuine calculation, simulation, data parsing/synthesis
DYNAMIC_PROMPTS = [
    # Numerical / Math / Algorithms
    "compute the eigenvalues of this 4x4 covariance matrix and output to eigenvalues.json",
    "calculate the trajectories of a double pendulum over 20 seconds and save to pendulum.csv",
    "work out the real and complex roots of this quartic polynomial into roots.txt",
    "solve this system of five linear equations using LU decomposition and save to solution.json",
    "simulate a 3D random walk with 5000 steps and save the displacement history to walk_3d.csv",
    "calculate the perimeter and polygon area from these GPS vertices and export to geom_metrics.json",
    "compute the rolling standard deviation and variance of these stock ticks into volatility.json",
    "simulate a predator-prey Lotka-Volterra model across 100 timesteps and write to simulation.csv",
    "calculate the first 100 prime numbers and their successive gaps into prime_gaps.txt",
    "compute the fast fourier transform of this discrete audio signal and save magnitudes to fft.json",
    "simulate Brownian motion for 100 particles and record final positions in particles.json",
    "compute the convex hull of these 2D points using the Graham scan algorithm into hull.json",
    "calculate the Fibonacci sequence up to index 200 with arbitrary precision into fib.txt",
    "solve the one-dimensional heat diffusion equation across a rod into heat_profile.csv",
    "compute the singular value decomposition of this matrix and store singular values in svd.json",
    "calculate the shortest path distances in this weighted graph using Dijkstra into distances.json",
    "simulate the Collatz sequence for all integers up to 1000 and record max sequence lengths in collatz.csv",
    "compute the linear regression coefficients and R-squared for these paired readings into regression.json",
    "simulate a three-body gravitational orbital system and save step coordinates to orbits.csv",
    "calculate numerical integration of the error function from 0 to 5 using Simpson's rule into integral.txt",
    "work out the eigenvalues and condition number of this Hilbert matrix into hilbert_stats.json",
    "simulate a Markov chain with 4 states across 1000 transitions and write state frequencies to markov.json",
    "calculate the geodesic distance between pairs of coordinate points and save to distances.csv",
    "compute the autocorrelation of this sensor time-series data and write lags to autocorr.json",
    "solve the Poisson equation on a 20x20 grid with Dirichlet boundary conditions into grid.csv",
    # Data Transformations / Log Parsing / Reports
    "parse nginx access logs and aggregate request count per status code into http_codes.json",
    "compile a summary table of failed SSH login attempts from auth.log into ssh_failures.txt",
    "parse this apache error log and compute the top 10 most frequent client IPs into top_ips.json",
    "extract API response latencies from request.log and calculate 95th and 99th percentiles into latencies.json",
    "parse sys_metrics.csv and generate a summary report of CPU utilization spikes into cpu_spikes.txt",
    "transform this nested json of customer orders into a flattened sales summary table in sales.csv",
    "aggregate total network bandwidth used per port from netflow.log into net_usage.json",
    "parse git log output and compute total commits and lines changed per author into author_stats.txt",
    "extract SQL slow query durations from db_slow.log and aggregate average execution time per table into query_summary.json",
    "parse memory allocation logs and compute peak heap usage per thread into thread_memory.json",
    "compile a summary table of HTTP 500 exceptions from app.log grouped by endpoint into error_table.txt",
    "parse docker daemon logs and count container crash events per image into crash_metrics.json",
    "extract disk I/O metrics from iostat.log and group average write times by device into disk_io.json",
    "aggregate daily weather measurements from sensor_dump.csv and compute monthly temperature averages into monthly_weather.csv",
    "transform this json array of telemetry events into a frequency distribution table in event_freqs.json",
    "parse audit.log to compute total user permission changes per role into role_audit.txt",
    "extract batch processing runtimes from job_history.csv and compute throughput per hour into throughput.json",
    "compile a summary report of kernel panic stack traces into kernel_analysis.txt",
    "parse load balancer metrics and compute request error rates per backend host into host_health.json",
    "aggregate page load timings from browser_rum.csv and create a latency distribution into rum_percentiles.json",
    # Algorithmic Generation / Plots / Visualizations
    "generate a 20x20 random maze grid using Prim's algorithm and save representation to maze.txt",
    "generate Mandelbrot set boundary coordinates at resolution 400x400 into mandelbrot.csv",
    "generate synthetic time-series data with Gaussian noise and seasonal trends into synthetic_series.csv",
    "generate a correlation matrix from multivariate sensor data and save heatmap data to correlation.json",
    "generate a frequency histogram bin table for these customer age values into age_histogram.csv",
    "generate a scatter plot coordinate dataset for k-means clustered data into clusters.json",
    "compute the Pareto front of this multi-objective optimization problem into pareto.json",
    "generate a cellular automaton Game of Life evolution matrix over 50 steps into life_steps.csv",
    "calculate the page rank scores for this web page link graph into pagerank.json",
    "generate a contingency table and chi-square test statistic from survey_responses.csv into chi_square.txt"
]

# 2. Known Capabilities (55 prompts): discrete system actions, app launches, git, files, settings
# Includes collision keywords: 'code', 'log', 'bar', 'table', 'python', 'report', 'folder', 'file'
KNOWN_PROMPTS = [
    # Application Launches (Collision words: code, terminal, pad)
    "open notepad",
    "launch calculator",
    "open visual studio code",  # Collision: 'code'
    "launch vivaldi browser",
    "open windows terminal",
    "launch cmd",
    "open powershell",
    "start task manager",
    "open file explorer",
    "launch edge",
    # System Capabilities (Collision words: report, log, bar, table)
    "generate battery report",  # Collision: 'report', 'generate' -> known capability generate_battery_report
    "show battery status",
    "check battery health report",  # Collision: 'report'
    "show available wifi networks",
    "scan wifi networks",
    "check system memory usage",
    "show total disk space",
    "display cpu usage",
    "take a screenshot",
    "capture screen",
    "lock workstation",
    "mute system audio",
    "unmute system audio",
    "list running processes",
    "get network ip address",
    "show hostname",
    "check uptime",
    # Git / Workspace Queries (Collision words: log, status)
    "get git status of current repository",
    "show git status",
    "view git branch",
    "check git status of project",
    # File Operations / Navigation (Collision words: file, folder, open)
    "open downloads folder",
    "open desktop directory",
    "open documents folder",
    "reveal file in explorer",
    "show output file in explorer",
    "open current project folder",
    # Collision cases targeting known system tools
    "open system event log in event viewer",  # Collision: 'log'
    "open taskbar settings",  # Collision: 'bar'
    "open character map",
    "open control panel",
    "open device manager",
    "open disk management",
    "open network connections",
    "open registry editor",
    "open services manager",
    "open windows settings",
    "open date and time settings",
    "open sound settings",
    "open display settings",
    "open bluetooth settings",
    "open installed apps list",  # Collision: 'list'
    "open default apps settings",
    "open clipboard settings",
    "open storage settings"
]

# 3. Conversational / Informational (55 prompts): questions, explanations, advice, chat, literature
# Includes collision keywords: 'plot', 'code', 'python', 'solve', 'log', 'count', 'summary', 'report', 'write', 'table'
CONVERSATIONAL_PROMPTS = [
    # Literature & Puzzles (Collisions: plot, solve, riddle)
    "what is the plot of hamlet?",  # Collision: 'plot'
    "can you explain the plot of the great gatsby?",  # Collision: 'plot'
    "summarize the main plot points of macbeth",  # Collision: 'plot', 'summarize'
    "help me solve this riddle: what has keys but no locks?",  # Collision: 'solve'
    "can you solve this lateral thinking puzzle about a man in an elevator?",  # Collision: 'solve'
    "how do i solve a dispute between team members amicably?",  # Collision: 'solve'
    "what is the best way to solve conflict in an engineering team?",  # Collision: 'solve'
    # Programming & Technical Concepts (Collisions: python, code, script, table)
    "what is python and where is it used?",  # Collision: 'python'
    "explain what a python decorator is conceptually",  # Collision: 'python', 'code'
    "what is the difference between a process and a thread in python?",  # Collision: 'python'
    "what does clean code mean in software engineering?",  # Collision: 'code'
    "what is the airport code for London Heathrow?",  # Collision: 'code'
    "what is the postal code format for Canada?",  # Collision: 'code'
    "why do programmers use pseudocode before writing real code?",  # Collision: 'code'
    "can you explain the periodic table of elements?",  # Collision: 'table'
    "what are the dimensions of a regulation table tennis table?",  # Collision: 'table'
    "what is the difference between TCP and UDP?",
    "explain the difference between synchronous and asynchronous execution",
    "what does acid compliance mean in relational databases?",
    "what is the cap theorem?",
    "how does public key cryptography work?",
    "explain the concept of recursion with an analogy",
    # Everyday Advice & Writing (Collisions: write, report, summary, log, count)
    "write an email thanking my mentor for their career guidance",  # Collision: 'write'
    "write a congratulatory note for a colleague who got promoted",  # Collision: 'write'
    "draft a polite decline message for an invitation",
    "give me a summary of the historical causes of World War One",  # Collision: 'summary'
    "can you give me a brief summary of the book Sapiens?",  # Collision: 'summary'
    "what was the Warren Commission report about?",  # Collision: 'report'
    "explain the difference between a captain's log and a diary",  # Collision: 'log'
    "how does an airplane flight data recorder or black box log information?",  # Collision: 'log'
    "count me in for the team lunch tomorrow",  # Collision: 'count'
    "can you explain why every vote should count in a democracy?",  # Collision: 'count'
    "what does it mean when someone says don't count your chickens before they hatch?",  # Collision: 'count'
    "how do astronauts sleep in zero gravity?",
    "why is the sky blue during the day and red at sunset?",
    "what causes ocean tides?",
    "who painted the Mona Lisa?",
    "what is the capital of Australia?",
    "how do noise cancelling headphones work?",
    "what is the difference between astronomy and astrology?",
    "why do leaves change color in autumn?",
    "can you suggest some healthy breakfast ideas?",
    "how can I improve my focus while studying?",
    "what is the difference between deductive and inductive reasoning?",
    # Greetings & Pleasantries
    "good morning, how are you today?",
    "hello there!",
    "thank you for your assistance",
    "have a great afternoon",
    "who are you and what is your purpose?",
    "tell me a clever programming joke",
    "can you tell me an interesting science trivia fact?",
    "what are three interesting facts about octopuses?",
    "how does photosynthesis convert sunlight into chemical energy?",
    "explain quantum superposition in simple terms",
    "can you recommend a good book about the history of computing?"
]

# 4. Clarification Required (55 prompts): underspecified, ambiguous, incomplete, nonsense
# Includes collision keywords: 'solve', 'calculate', 'compute', 'open', 'code', 'plot', 'file', 'save'
CLARIFICATION_PROMPTS = [
    # Single-word / truncated commands (Collisions: solve, compute, calculate, plot, code)
    "solve",  # Collision: 'solve' with zero arguments
    "calculate",  # Collision: 'calculate' with zero arguments
    "compute",  # Collision: 'compute' with zero arguments
    "plot",  # Collision: 'plot' with zero arguments
    "code",  # Collision: 'code' with zero arguments
    "script",  # Collision: 'script' with zero arguments
    "run",
    "start",
    "open",
    "save",
    "delete",
    "check",
    "inspect",
    "do",
    "help",
    "convert",
    "generate",
    "summary",
    # Highly ambiguous phrases lacking context or operands
    "run the thing",
    "do that task for me",
    "fix the problem",
    "continue what we were doing",
    "process it now",
    "start the job",
    "make it work",
    "show me",
    "find the file",  # Missing filename or search pattern
    "save it to disk",  # Missing content and filename
    "delete that folder",  # Missing target folder
    "open the application",  # Missing app name
    "calculate the result",  # Missing formula or numbers
    "solve the equation",  # Missing equation
    "compute the numbers",  # Missing dataset
    "plot the chart",  # Missing data
    "parse the log",  # Missing log path or type
    "send it over",
    "update the settings",
    "clean up everything",
    "handle this please",
    # Incomplete syntax / sentence fragments
    "can you please",
    "i would like to",
    "where is the",
    "how do i get to",
    "because of the",
    "if you can then",
    # Nonsense / keyboard mashing / corrupt input
    "asdfghjkl",
    "qwertyuiop zxcvbnm",
    "1234567890 !@#$%^",
    "banana potato spaceship umbrella",
    "purple elephant dancing backwards on ceiling",
    "blablabla whatever whatever",
    "??? !!! ???",
    "............",
    "undefined null NaN void",
    "foo bar baz qux corge"
]


def build_manifest() -> dict:
    items = []
    idx = 1

    # Add Dynamic Computation (55)
    for p in DYNAMIC_PROMPTS:
        items.append({
            "id": f"BLIND-{idx:03d}",
            "category": "dynamic_computation",
            "prompt": p,
            "expected_intent_class": "DYNAMIC_COMPUTATION",
            "expected_intent": "execute_dynamic_tool",
            "expected_tier": "LOCAL_MODEL",
            "is_collision_case": any(w in p.lower() for w in ("table", "report", "summary", "count", "log")),
        })
        idx += 1

    # Add Known Capabilities (55)
    for p in KNOWN_PROMPTS:
        items.append({
            "id": f"BLIND-{idx:03d}",
            "category": "known_capability",
            "prompt": p,
            "expected_intent_class": "KNOWN_CAPABILITY",
            "expected_intent": "KNOWN_OR_SYSTEM_CAPABILITY",
            "expected_tier": "DETERMINISTIC_OR_SEMANTIC",
            "is_collision_case": any(w in p.lower() for w in ("code", "log", "bar", "table", "report", "generate")),
        })
        idx += 1

    # Add Conversational (55)
    for p in CONVERSATIONAL_PROMPTS:
        items.append({
            "id": f"BLIND-{idx:03d}",
            "category": "conversational",
            "prompt": p,
            "expected_intent_class": "CONVERSATIONAL",
            "expected_intent": "conversational_dialogue",
            "expected_tier": "LOCAL_MODEL",
            "is_collision_case": any(w in p.lower() for w in ("plot", "code", "python", "solve", "log", "table", "write", "summary", "report", "count")),
        })
        idx += 1

    # Add Clarification Required (55)
    for p in CLARIFICATION_PROMPTS:
        items.append({
            "id": f"BLIND-{idx:03d}",
            "category": "clarification_required",
            "prompt": p,
            "expected_intent_class": "CLARIFICATION_REQUIRED",
            "expected_intent": "needs_clarification",
            "expected_tier": "CLARIFICATION",
            "is_collision_case": any(w in p.lower() for w in ("solve", "calculate", "compute", "plot", "code", "generate", "summary")),
        })
        idx += 1

    raw_json = json.dumps(items, indent=2, sort_keys=True)
    digest = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()

    manifest = {
        "phase": "F0-25F.3",
        "stage": "STAGE 6 — FREEZE ROUTING BLIND HOLDOUT MANIFEST",
        "total_prompts": len(items),
        "class_distribution": {
            "DYNAMIC_COMPUTATION": len(DYNAMIC_PROMPTS),
            "KNOWN_CAPABILITY": len(KNOWN_PROMPTS),
            "CONVERSATIONAL": len(CONVERSATIONAL_PROMPTS),
            "CLARIFICATION_REQUIRED": len(CLARIFICATION_PROMPTS),
        },
        "collision_cases_count": sum(1 for it in items if it["is_collision_case"]),
        "sha256": digest,
        "prompts": items,
    }
    return manifest


def main():
    manifest = build_manifest()
    out_file = REPO_ROOT / "docs" / "audit" / "F0_25F3_ROUTING_BLIND_MANIFEST.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Routing blind holdout manifest created:")
    print(f"  Total prompts: {manifest['total_prompts']}")
    print(f"  Classes: {manifest['class_distribution']}")
    print(f"  Collision cases: {manifest['collision_cases_count']}")
    print(f"  SHA256: {manifest['sha256']}")
    print(f"  Artifact written to: {out_file}")


if __name__ == "__main__":
    main()
