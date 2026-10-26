# Stockfish CPU budget on Windows

Open **Engine → Stockfish CPU budget** and choose **10%, 25%, 50%, 75%**, or **Unrestricted (100%)**. The default is Unrestricted. Your selection is saved and reapplied when an external UCI engine starts.

Threads and CPU budget are independent. For a 9800X3D, you can leave Threads at 16 and start with a 25% budget. This caps the engine's combined CPU use at roughly one quarter of the machine's total CPU capacity; it does not pin each thread to a fixed duty cycle or guarantee performance equivalent to four unrestricted threads. Lower budgets can reduce heat and fan noise, and reduce search throughput. Searches with a wall-time limit may reach less depth.

Changes apply to the running engine without restarting its search. Unrestricted disables rate control. The GUI and Maia worker remain outside the engine's job object, and Windows power settings are unchanged. Other configured UCI engines receive the same budget.

The implementation uses Windows Job Object CPU rate control with a hard cap. If the cap cannot be applied at launch, the engine stops with an error rather than running without the requested limit. A rejected live change shows an error and retains the previous saved choice. The menu is disabled on other operating systems.

The Windows test assigns a real subprocess to a job, verifies the rate-control flags and rates for several budgets, disables the cap, and verifies cleanup. This verifies OS configuration; noise levels depend on hardware, cooling and other workloads.
