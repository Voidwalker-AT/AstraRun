"""Generator and sealer for F0-25F.4 Routing Blind Holdout Manifest (320 prompts, balanced 80x4).

Constructs an authoritative, balanced blind holdout of 320 prompts (80 per class)
designed to evaluate recall, precision, and lexical collision resilience:
- 80 DYNAMIC_COMPUTATION prompts
- 80 KNOWN_CAPABILITY prompts
- 80 CONVERSATIONAL prompts
- 80 CLARIFICATION_REQUIRED prompts

Generates and seals: docs/audit/F0_25F4_ROUTING_BLIND_MANIFEST.json
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DYNAMIC_PROMPTS = [
    # Math & Numerical Algorithms (30)
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
    "compute the Cholesky decomposition of this symmetric positive-definite matrix into cholesky.json",
    "solve a system of nonlinear differential equations using Runge-Kutta 4th order into rk4_output.csv",
    "calculate prime factorizations for all composite numbers up to 500 into factors.json",
    "simulate a two-dimensional cellular automaton for 250 steps and save grid history to ca_grid.csv",
    "calculate the determinant and matrix inverse of this 5x5 matrix into matrix_inv.json",

    # Data Pipelines & Transformations (30)
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
    "parse payment gateway webhook logs and aggregate settlement failure reasons into settlement_fails.csv",
    "compile a summary report of kernel panic stack traces into kernel_analysis.txt",
    "extract user login session durations from auth.csv and compute median session length into session_stats.json",
    "parse load balancer access logs and compute average response payload size by URI into uri_payloads.json",
    "transform raw JSON sensor telemetry into a pivot table of hourly averages in pivot_table.csv",
    "parse redis slowlog entries and compute command frequency breakdown into redis_stats.json",
    "extract microservice trace spans and compute latency bottlenecks per service into span_latencies.csv",
    "aggregate e-commerce cart abandonments by product category into cart_abandonment.json",
    "parse firewall drop logs and aggregate blocked traffic by destination port into firewall_blocks.csv",
    "extract memory leak candidates from heap profiler dump into heap_candidates.json",
    "aggregate temperature sensor anomalies exceeding 3 sigma into temperature_anomalies.csv",
    "parse build artifact timing logs and compute compilation bottlenecks per module into build_bottlenecks.json",
    "transform unstructured customer review text into word frequency counts in word_freqs.json",
    "extract database deadlock events from postgres.log into deadlocks_summary.txt",
    "compile a summary table of container resource throttle events into container_throttles.csv",

    # Procedural Generation & Plot Data (20)
    "generate a 25x25 random maze using depth-first search and save ASCII layout to maze.txt",
    "generate synthetic time-series data for 10 simulated IoT temperature nodes into iot_nodes.csv",
    "generate a correlation matrix from multivariate sensor data and save heatmap data to correlation.json",
    "generate a frequency histogram bin table for these customer age values into age_histogram.csv",
    "generate a scatter plot coordinate dataset for k-means clustered data into clusters.json",
    "generate a synthetic test dataset of 500 mock user profiles with addresses into mock_users.json",
    "generate Mandelbrot set boundary coordinates at zoom level 4 into mandelbrot_coords.csv",
    "generate a 2D heightmap grid using Perlin noise algorithm and save to heightmap.csv",
    "generate a line chart coordinate dataset for exponential decay curves into decay_chart.json",
    "generate a Pareto front dataset for multi-objective optimization into pareto_front.csv",
    "generate a synthetic dataset of financial transactions with planted fraud anomalies into transactions.csv",
    "generate a Delaunay triangulation network from 50 random 2D vertices into triangulation.json",
    "generate a synthetic population demographic pyramid distribution into demographics.csv",
    "generate an adjacency matrix for a scale-free Barabasi-Albert network into network_matrix.csv",
    "generate a synthetic sales forecast with seasonal ARIMA noise into forecast.csv",
    "generate a Voronoi diagram cell partition dataset for 40 seeds into voronoi_cells.json",
    "generate a 2D Gaussian mixture distribution sample into gaussian_samples.csv",
    "generate synthetic server workload patterns for stress testing into stress_workload.csv",
    "generate a synthetic stock price order book simulation history into order_book.csv",
    "generate a decision tree split coordinate dataset into tree_splits.json",
]

KNOWN_CAPABILITY_PROMPTS = [
    # System Controls & Monitors (25)
    "mute the system volume",
    "unmute system audio",
    "lock my workstation",
    "lock this computer",
    "check current system memory usage",
    "show available disk space on drive C",
    "take a screenshot of the entire desktop",
    "capture a screenshot right now",
    "generate battery report into Downloads",
    "create a Windows battery report",
    "scan available wifi networks",
    "show nearby wifi networks",
    "show current wifi status",
    "check my wifi connection",
    "get system information and uptime",
    "show computer hostname and OS version",
    "list running processes on this machine",
    "what processes are currently running?",
    "check cpu load on workstation",
    "inspect open network ports",
    "check if port 8080 is listening",
    "check if port 443 is active",
    "find file report.pdf in Documents",
    "search for config.json in user folder",
    "show downloads folder in explorer",

    # Application Management (25)
    "open notepad",
    "launch calculator",
    "start windows terminal",
    "open visual studio code",
    "launch file explorer",
    "open task manager",
    "start edge browser",
    "open settings",
    "launch command prompt",
    "open powershell",
    "close notepad",
    "close calculator",
    "close windows terminal",
    "exit file explorer",
    "close edge browser",
    "is notepad currently running?",
    "check if calculator is open",
    "is visual studio code running?",
    "do i have notepad installed?",
    "check if vivaldi is installed",
    "is edge browser installed?",
    "minimize the active window",
    "maximize this window",
    "bring notepad to foreground",
    "switch to calculator window",

    # Lexical Collisions (30) - contain 'report', 'summary', 'log', 'scan', 'code', 'plot', 'table' but ARE KNOWN CAPABILITIES
    "generate battery report",
    "save battery report to downloads",
    "show battery report",
    "produce a battery health report",
    "check battery health report",
    "scan wifi networks in area",
    "scan for available wireless signals",
    "perform wifi scan",
    "show wifi scan list",
    "open git status in repository",
    "show git log of recent commits",
    "view repository git status",
    "check git branch status",
    "show system summary",
    "display system hardware summary",
    "open summary of running tasks",
    "inspect system event log viewer",
    "open event log settings",
    "open visual studio code editor",
    "start code editor",
    "launch code application",
    "open character map table",
    "open ascii character table",
    "inspect routing table in network connections",
    "view network adapter connections table",
    "show installed apps table in settings",
    "open bluetooth settings",
    "open display settings",
    "open sound settings",
    "take screenshot of active window",
]

CONVERSATIONAL_PROMPTS = [
    # Inquiries & Questions (25)
    "why is the sky blue?",
    "can you explain what a race condition is in multi-threaded programming?",
    "how does public key cryptography work?",
    "what is the difference between TCP and UDP?",
    "could you explain how garbage collection works in Python?",
    "what was the primary cause of the Bronze Age collapse?",
    "how does a quantum computer differ from a classical computer?",
    "explain the concept of event-driven architecture",
    "what is the purpose of an index in a relational database?",
    "how do convolutional neural networks process images?",
    "what causes ocean tides on Earth?",
    "why do leaves change color in the autumn?",
    "what is the difference between processes and threads?",
    "how does DNS resolution work across the internet?",
    "can you explain the CAP theorem for distributed systems?",
    "what is the significance of the Turing test?",
    "how does virtual memory paging work in Windows?",
    "what is the difference between symmetric and asymmetric encryption?",
    "can you explain how gradient descent optimizes neural networks?",
    "why does time dilation occur in special relativity?",
    "what are the main principles of functional programming?",
    "how does raft consensus maintain cluster state?",
    "what is the difference between stack and heap memory?",
    "why is cache coherence important in multi-core processors?",
    "how does TLS handshake establish a secure connection?",

    # Advice, Decisions & Casual (25)
    "good morning Astra, how are you today?",
    "hello there, thanks for your help earlier",
    "have a wonderful day!",
    "thank you very much for assisting me",
    "who are you and what are your main capabilities?",
    "help me decide between learning Rust or Go this semester",
    "should I use PostgreSQL or MongoDB for an e-commerce catalog?",
    "help me choose between AWS and Azure for a small startup",
    "what are some best practices for writing clean unit tests?",
    "how should I structure my daily schedule to avoid burnout?",
    "can you give me advice on conducting technical interviews?",
    "what are good strategies for managing technical debt in legacy codebases?",
    "help me choose a good database migration strategy for zero downtime",
    "how should I organize microservices repositories: mono-repo or multi-repo?",
    "what are some tips for improving deep work concentration?",
    "can you recommend a good book on distributed systems design?",
    "how do I give constructive code review feedback without offending peers?",
    "what should I consider before switching from monolith to microservices?",
    "how can our engineering team improve sprint velocity estimation?",
    "what are the trade-offs between serverless and containerized deployments?",
    "what is the best way to prepare for an architecture review meeting?",
    "how should I approach learning a completely unfamiliar codebase?",
    "can you suggest techniques for effective debugging under pressure?",
    "what are good principles for designing developer-friendly REST APIs?",
    "how can I build resilience into background job worker queues?",

    # Lexical Collisions (30) - contain 'code', 'plot', 'solve', 'table', 'calculate', 'python', 'summary', 'report', 'count' but ARE CONVERSATIONAL
    "what does the phrase clean code mean to software engineers?",
    "can you summarize the main plot of Hamlet?",
    "who wrote the play Romeo and Juliet and what is its plot?",
    "what is the plot of the novel 1984 by George Orwell?",
    "how do I solve a personality conflict between two team members?",
    "help me solve a dispute over code formatting standards",
    "can you help me solve this lateral thinking puzzle about a lighthouse?",
    "who painted the periodic table mural at the university?",
    "what are the standard dimensions of a regulation ping pong table?",
    "can you write a congratulatory email to a colleague who got promoted?",
    "draft a polite decline letter for a conference speaking invitation",
    "what is the airport code for Tokyo Haneda airport?",
    "what is the postal code format used in London?",
    "can you summarize the key findings of the Warren Commission report?",
    "what was recorded in the historic Apollo 11 captain's log?",
    "what does black box flight recorder log during an aircraft incident?",
    "can you calculate how many days are between Halloween and Christmas in your head?",
    "how does a chef work out the right balance of spices in a curry?",
    "why does the idiom don't count your chickens before they hatch exist?",
    "explain why every citizen's vote should count equally in a democracy",
    "what did Monty Python have to do with the naming of Python programming language?",
    "tell me the story of how Python got its name from British comedy",
    "can you explain what a truth table is in formal propositional logic?",
    "what is the difference between a coffee table and an end table?",
    "who holds the world record for the highest table tennis rally count?",
    "can you summarize the history of the periodic table of elements?",
    "how do directors plot camera angles in a film storyboard?",
    "what does the word solve mean in the context of forensic crime investigations?",
    "can you summarize the plot of Christopher Nolan's film Inception?",
    "count me in for the team outing, sounds like a lot of fun!",
]

CLARIFICATION_REQUIRED_PROMPTS = [
    # Underspecified / Ambiguous commands (30)
    "do something",
    "help me with this",
    "fix the problem",
    "start the task",
    "run it now",
    "handle the situation",
    "open the file",
    "save it to disk",
    "delete that folder",
    "calculate the result",
    "solve the equation",
    "compute the numbers",
    "plot the chart",
    "parse the log",
    "generate the report",
    "process the data",
    "check the thing",
    "inspect the window",
    "show me that",
    "find the document",
    "run the process",
    "make it work",
    "update the system",
    "send the payload",
    "connect to it",
    "restart the application",
    "clean up the workspace",
    "convert the input",
    "transform the output",
    "organize the files",

    # Vague conversational fragments & placeholders (25)
    "can you please",
    "i would like to",
    "where is the",
    "how do i get to",
    "because of the issue",
    "if you can then",
    "continue what we were doing yesterday",
    "do the same thing you did last time",
    "pick up from where we stopped",
    "use that previous value from earlier",
    "apply the same changes to the other one",
    "what happened to that task?",
    "did it finish yet?",
    "try running it again with different parameters",
    "change the setting like we talked about",
    "make the adjustment you suggested",
    "proceed with option number two",
    "yes go ahead with that",
    "no not that one the other one",
    "can you check on it?",
    "what was the name of that thing again?",
    "is it supposed to look like that?",
    "why did that happen just now?",
    "could you fix that error for me?",
    "put it back the way it was before",

    # Lexical Collisions & Bare Verbs (25)
    "solve",
    "calculate",
    "compute",
    "plot",
    "code",
    "script",
    "generate",
    "summary",
    "table",
    "report",
    "count",
    "log",
    "python",
    "wifi",
    "battery",
    "asdfghjkl",
    "qwertyuiop",
    "zxcvbnm",
    "blablabla",
    "??? !!! ???",
    "............",
    "undefined null nan void",
    "--- === +++",
    "run script",
    "generate table",
]


def main():
    prompts_manifest = []
    
    # 1. Dynamic
    for idx, p in enumerate(DYNAMIC_PROMPTS, 1):
        prompts_manifest.append({
            "id": f"BLIND-DYN-{idx:03d}",
            "prompt": p,
            "expected_intent_class": "DYNAMIC_COMPUTATION",
            "is_collision_case": False,
        })
        
    # 2. Known
    for idx, p in enumerate(KNOWN_CAPABILITY_PROMPTS, 1):
        prompts_manifest.append({
            "id": f"BLIND-CAP-{idx:03d}",
            "prompt": p,
            "expected_intent_class": "KNOWN_CAPABILITY",
            "is_collision_case": idx > 50,
        })
        
    # 3. Conversational
    for idx, p in enumerate(CONVERSATIONAL_PROMPTS, 1):
        prompts_manifest.append({
            "id": f"BLIND-CONV-{idx:03d}",
            "prompt": p,
            "expected_intent_class": "CONVERSATIONAL",
            "is_collision_case": idx > 50,
        })
        
    # 4. Clarification
    for idx, p in enumerate(CLARIFICATION_REQUIRED_PROMPTS, 1):
        prompts_manifest.append({
            "id": f"BLIND-CLAR-{idx:03d}",
            "prompt": p,
            "expected_intent_class": "CLARIFICATION_REQUIRED",
            "is_collision_case": idx > 55,
        })

    total = len(prompts_manifest)
    assert total == 320, f"Expected exactly 320 prompts, got {total}"

    # Calculate content SHA256 (canonical JSON of the prompt list)
    prompt_bytes = json.dumps(prompts_manifest, sort_keys=True, indent=2).encode("utf-8")
    content_sha256 = hashlib.sha256(prompt_bytes).hexdigest()

    manifest_data = {
        "phase": "F0-25F.4",
        "benchmark": "ROUTING_BLIND_HOLDOUT_320",
        "sha256": content_sha256,
        "total_prompts": total,
        "class_distribution": {
            "DYNAMIC_COMPUTATION": len(DYNAMIC_PROMPTS),
            "KNOWN_CAPABILITY": len(KNOWN_CAPABILITY_PROMPTS),
            "CONVERSATIONAL": len(CONVERSATIONAL_PROMPTS),
            "CLARIFICATION_REQUIRED": len(CLARIFICATION_REQUIRED_PROMPTS),
        },
        "collision_cases_count": sum(1 for p in prompts_manifest if p["is_collision_case"]),
        "prompts": prompts_manifest,
    }

    out_file = REPO_ROOT / "docs" / "audit" / "F0_25F4_ROUTING_BLIND_MANIFEST.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
    print(f"Generated and sealed {total} blind prompts to {out_file}")
    print(f"Manifest SHA256: {content_sha256}")


if __name__ == "__main__":
    main()
