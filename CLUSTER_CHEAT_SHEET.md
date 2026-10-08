# Cluster Cheat Sheet

**Purpose:** Single source of truth for cluster configuration, setup, and troubleshooting.  
**Updated:** 2026-10-07  
**Owner:** Karla Gonzalez (kvrlv)

---

## Section 1: Cluster Basics

### Connection

```bash
# SSH into cluster
 ssh -i C:\Users\kvrlv\.ssh\id_ed25519 gonzalez@137.94.124.1

# Check if already connected
hostname
whoami
pwd
```

**Status:**
- [X] Cluster hostname: `_MCSDLC-LOGIN___`
- [X] Username on cluster: `__gonzalez________`
- [ ] SSH key configured: YES
- [ ] Can SSH without password: NO

**Connection string:**
```bash
# Copy-paste ready
ssh kvrlv@[TO_BE_FILLED]
```

---

### System Info

**Discover (run on cluster):**
```bash
uname -a                    # OS and kernel
cat /etc/os-release         # Linux distro
nproc                       # Total CPU cores
free -h                     # Total RAM
nvidia-smi                  # GPU info (if available)
lsb_release -a              # Distro details
```

**Actual output:**
```
OS: 
Linux MCSDLC-LOGIN 6.8.0-138-generic #138~22.04.1-Ubuntu SMP PREEMPT_DYNAMIC Fri Aug  7 13:43:15 UTC  x86_64 x86_64 x86_64 GNU/Linux
____________________________
Kernel: 
PRETTY_NAME="Ubuntu 22.04.5 LTS"
NAME="Ubuntu"
VERSION_ID="22.04"
VERSION="22.04.5 LTS (Jammy Jellyfish)"
VERSION_CODENAME=jammy
ID=ubuntu
ID_LIKE=debian
HOME_URL="https://www.ubuntu.com/"
SUPPORT_URL="https://help.ubuntu.com/"
BUG_REPORT_URL="https://bugs.launchpad.net/ubuntu/"
PRIVACY_POLICY_URL="https://www.ubuntu.com/legal/terms-and-policies/privacy-policy"
UBUNTU_CODENAME=jammy
____________________________
CPUs available: 
40
____________________________
RAM available: 
             total        used        free      shared  buff/cache   available
Mem:            31Gi       6.0Gi       883Mi       0.0Ki        24Gi        24Gi
Swap:          2.0Gi       558Mi       1.5Gi
____________________________
GPUs: ____________________________
```

---

## Section 2: SLURM Configuration

### SLURM Commands

```bash
# Check cluster status
sinfo                       # Show all partitions


PARTITION    AVAIL  TIMELIMIT  NODES  STATE NODELIST
gtx1080*        up   infinite     12  down* MCSDLC-GTX1080-[01-12]
test            up   infinite      1   idle MCSDLC-TEST-1
lsrcpushort     up    8:00:00      2   idle MCSDLC-LSR-CPU-[1-2]
lsrcpumid       up 5-00:00:00      2   idle MCSDLC-LSR-CPU-[1-2]
lsrcpulong      up   infinite      2   idle MCSDLC-LSR-CPU-[1-2]
dgxv100short    up    8:00:00      1    mix MCSDLC-DGX-V100-1
dgxv100mid      up 5-00:00:00      1    mix MCSDLC-DGX-V100-1
dgxv100long     up   infinite      1    mix MCSDLC-DGX-V100-1
dgxh100short    up    8:00:00      1    mix MCSDLC-DGX-H100-1
dgxh100mid      up 5-00:00:00      1    mix MCSDLC-DGX-H100-1
dgxh100long     up   infinite      1    mix MCSDLC-DGX-H100-1

# Check your jobs
squeue --me                 # Your current jobs
squeue -u kvrlv             # Explicit user

# Submit a job
sbatch my_script.slurm

# Check job details
scontrol show job [JOBID]

# Cancel job
scancel [JOBID]

# Get job output (while running or after)
tail -f slurm-[JOBID].out
```

**Status:**
- [X] SLURM available: YES 
- [X] `sinfo` works: YES 

### Available Partitions

**Discover:**
```bash
sinfo -o "%P %D %T %c %m %G"
# Columns: Partition, Nodes, State, CPUs, Memory, GPUs
```

**Actual partitions:**

PARTITION NODES STATE CPUS MEMORY GRES
gtx1080* 12 down* 40 32048 gpu:gtx1080:2
test 1 idle 40 64258 gpu:rtx4090:1
lsrcpushort 2 idle 384 773574 (null)
lsrcpumid 2 idle 384 773574 (null)
lsrcpulong 2 idle 384 773574 (null)
dgxv100short 1 idle 80 515843 gpu:v100:8
dgxv100mid 1 idle 80 515843 gpu:v100:8
dgxv100long 1 idle 80 515843 gpu:v100:8
dgxh100short 1 mixed 224 2063936 gpu:h100:8

| Partition | Nodes | CPUs/Node | RAM/Node | GPUs | Max Time | Use Case |
|-----------|-------|-----------|----------|------|----------|----------|
| `_____` | `_` | `__` | `__` | `__` | `____` | CPU-only jobs |
| `_____` | `_` | `__` | `__` | `__` | `____` | GPU jobs |
| `_____` | `_` | `__` | `__` | `__` | `____` | Long-running |
| `_____` | `_` | `__` | `__` | `__` | `____` | Interactive |

**Default partition:** `_________________________`

---

### QoS (Quality of Service)

**Discover:**
```bash
sacctmgr show qos format=Name,MaxCPUPerUser,MaxSubmit
```

**Example job headers:**
```bash
#SBATCH --partition=cpu
#SBATCH --qos=normal
#SBATCH --time=01:00:00
#SBATCH --nodes=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
```

---

## Section 3: Python & Environment

### Python Versions Available

**Discover:**
```bash
# Method 1: Module system
module avail python
module avail Python

# Method 2: Direct search
which python
which python3
python --version
python3 --version
```

**Available versions:**

| Version | Available | Path | Notes |
|---------|-----------|------|-------|
| 3.8 | [ ] | `_________________________` | |
| 3.9 | [ ] | `_________________________` | |
| 3.10 | [ ] | `_________________________` | |
| 3.11 | [X] | `/home/users/gonzalez/miniconda3/envs/pr-framing/bin/python` | Python 3.11.15|
| 3.12 | [ ] | `_________________________` | |

**Recommended:** Python 3.11 or 3.10

### Module System

**Discover:**
```bash
module --version            # Check system
module load python/3.11     # Try loading (adjust version)
module list                 # See loaded modules
module avail | grep -i python
```

**Module command (if available):**
```bash
# Check if module system exists
type module

# If not found, check for other env managers
which conda
/home/users/gonzalez/miniconda3/condabin/conda```

**Status:**
- [X] Module system available: NO
module: command not found
- [X] Conda available: YES
- [ ] Load Python command: `module load ____________________`

---

### Virtual Environments

**Setup (one time):**
```bash
# Option A: Use cluster system Python + venv
python3 -m venv ~/codebook_aidev_env
source ~/codebook_aidev_env/bin/activate

# Option B: Use Conda (if available)
conda create -n codebook_aidev python=3.11
conda activate codebook_aidev

# Install required packages
pip install pandas polars scikit-learn matplotlib seaborn numpy scipy
```

**Activate in job scripts:**
```bash
# In .slurm file:
source ~/codebook_aidev_env/bin/activate
# OR:
conda activate codebook_aidev
```

**Status:**
- [ ] Venv created: YES / NO / PATH: `_________________________`
- [ ] Packages installed: YES / NO
- [ ] Test: `python -c "import pandas; print(pandas.__version__)"`

---

## Section 4: Storage & Data Access

### Storage Paths

```bash
# Discover on cluster:
echo $HOME                  # Home directory
echo $SCRATCH               # Scratch (if available)
echo $TMPDIR                # Temporary (if available)
df -h                       # All mounted filesystems
```

**Available storage:**

| Path | Quota | Purge Policy | Use Case |
|------|-------|--------------|----------|
| `$HOME` | `_____` | `_____` | Permanent data, code |
| `$SCRATCH` | `_____` | `_____` | Large job outputs (auto-deleted) |
| `$TMPDIR` | `_____` | `_____` | Temporary files |
| `/work/` | `_____` | `_____` | Shared group storage |

**Working directory:**
```bash
# Where to clone the project
export PROJECT_HOME=/path/to/Codebook_AIDev
# Or:
export PROJECT_HOME=$HOME/Codebook_AIDev
# Or:
export PROJECT_HOME=$SCRATCH/Codebook_AIDev
```

### Data Transfer

**From local → cluster:**
```bash
# Copy files
scp -r /path/to/local/data kvrlv@[CLUSTER]:/path/to/remote/

# Or use rsync (faster for large datasets)
rsync -avz /path/to/local/data kvrlv@[CLUSTER]:/path/to/remote/
```

**From cluster → local:**
```bash
scp -r kvrlv@[CLUSTER]:/path/to/remote/results ./local_results/
```

**Status:**
- [ ] Project cloned on cluster: YES / NO / PATH: `_________________________`
- [ ] Data accessible on cluster: YES / NO
- [ ] Data path on cluster: `results/tables/` ← Is this local or mounted?

---

## Section 5: Debugging & Troubleshooting

### Common Errors & Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `Command 'python' not found` | Python not in PATH | `module load python/3.11` or use `python3` |
| `sbatch: command not found` | Not on cluster or SLURM not loaded | Verify SSH connection, check `which sbatch` |
| `Job exceeds QoS limits` | Requested resources too high | Reduce `--time`, `--mem`, or `--cpus-per-task` |
| `Cannot access /path/to/data` | Path doesn't exist on cluster | Check `pwd`, use absolute paths, verify rsync |
| `ImportError: pandas` | Packages not installed | Activate venv/conda with `source activate` |
| `zcat: command not found` | gzip utilities missing | Load `module load gzip` or use Python `gzip` |

### Job Debugging

**Check job status:**
```bash
squeue -u kvrlv
scontrol show job [JOBID]
```

**View job output:**
```bash
# While running
tail -f slurm-[JOBID].out

# After completion
cat slurm-[JOBID].out
cat slurm-[JOBID].err
```

**Kill stuck job:**
```bash
scancel [JOBID]
```

**Run interactive job (for testing):**
```bash
salloc --partition=cpu --cpus-per-task=4 --mem=16G --time=00:30:00
# Then run commands directly in the allocated shell
```

---

## Section 6: Codebook_AIDev on Cluster

### Setup (first time)

```bash
# SSH to cluster
ssh kvrlv@[CLUSTER_HOST]

# Navigate to working directory (pick one)
cd $SCRATCH              # If using scratch
# OR:
cd $HOME                 # If using home

# Clone project
git clone https://github.com/[YOUR_ORG]/Codebook_AIDev.git
cd Codebook_AIDev

# Activate Python environment
source ~/codebook_aidev_env/bin/activate

# Verify structure
ls -la results/tables/table4_entities/
```

### Running Phase 1 on Cluster

```bash
# Copy job script (if not already in repo)
cp jobs/consolidate_table4.slurm .

# Edit job script with cluster-specific paths
# Update:
#SBATCH --partition=cpu        # ← use actual partition name
#SBATCH --mem=16G              # ← adjust if needed
# cd /path/to/Codebook_AIDev   # ← use actual path

# Submit
sbatch jobs/consolidate_table4.slurm

# Monitor
squeue --me
tail -f logs/consolidate_*.log

# When done, check output
ls -lh results/tables/table4_entities.csv
```

### Environment Variables

**Set in `.bashrc` or `.slurm` file:**
```bash
export PROJECT_HOME=/path/to/Codebook_AIDev
export DATA_INPUT=$PROJECT_HOME/results/tables/table4_entities
export DATA_OUTPUT=$PROJECT_HOME/results/tables
export PYTHONUNBUFFERED=1          # Flush output immediately
export OMP_NUM_THREADS=4           # For numpy/scipy parallelization
```

---

## Section 7: Performance Tips

### For Python Jobs

1. **Use appropriate partition:**
   ```bash
   #SBATCH --partition=cpu      # For Table 4 consolidation (no GPU needed)
   ```

2. **Allocate enough RAM:**
   ```bash
   #SBATCH --mem=16G            # For 1M-row CSV operations
   ```

3. **Use chunks/parallelization:**
   - Consolidation script already does this (see `--chunk-size`)
   - Don't load entire 1M-row table into memory at once

4. **Monitor job:**
   ```bash
   sstat --format AveCPU,AveRSS,MaxRSS -j [JOBID]
   ```

### Expected Performance

| Task | Local (Windows/Mac) | Cluster (HPC) |
|------|---------------------|---------------|
| Consolidate 1M rows | 5–10 min | 1–3 min (parallel) |
| Validate schema | <1 min | <1 min |
| Build coverage index | 2–3 min | <1 min |

---

## Section 8: Checklist for First Cluster Job

- [ ] SSH access working
- [ ] Python 3.11+ installed / module available
- [ ] Venv created and activated
- [ ] Required packages installed (pandas, scikit-learn, etc.)
- [ ] Project cloned on cluster
- [ ] Data accessible (results/tables/table4_entities/)
- [ ] SLURM job script created with correct paths
- [ ] Job script tested locally first
- [ ] sbatch submission successful
- [ ] Job output checked and validated

---

## Section 9: Reference Links & Contacts

**SLURM Documentation:**
- Quick start: https://slurm.schedmd.com/quickstart.html
- Job script examples: https://slurm.schedmd.com/sbatch.html

**Cluster-Specific:**
- [ ] Cluster docs: `_________________________`
- [ ] Cluster support email: `_________________________`
- [ ] Cluster wiki: `_________________________`

**Internal:**
- Phase 1 script: `src/tables/consolidate_entities.py`
- Job template: `jobs/consolidate_table4.slurm`
- Validation: `src/tables/validate_consolidated.py`

---

## Fill-in Template

**Copy this section, fill in with your cluster details, and add to top of doc:**

```markdown
## Cluster: [NAME]

**Host:** [HOSTNAME]
**OS:** [LINUX_DISTRO]
**Python:** module load python/3.11
**Partition for CPU jobs:** [NAME] (4 CPUs, 16G RAM default)
**Partition for GPU jobs:** [NAME] (if available)
**Home directory:** $HOME
**Scratch directory:** $SCRATCH
**Project location:** $SCRATCH/Codebook_AIDev
**Module load command:** module load python/3.11
**Virtual env:** $HOME/codebook_aidev_env (activate: `source ~/codebook_aidev_env/bin/activate`)
**Support contact:** [EMAIL]
```

