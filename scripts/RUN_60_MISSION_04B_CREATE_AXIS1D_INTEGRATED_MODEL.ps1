Set-Location $PSScriptRoot\..
matlab -nosplash -nodesktop -r "try, addpath(fullfile(pwd,'matlab_bridge')); RUN_MISSION_04B_CREATE_AXIS1D_INTEGRATED_MODEL_R2023B; catch ME, disp(getReport(ME,'extended','hyperlinks','off')); exit(1); end"
