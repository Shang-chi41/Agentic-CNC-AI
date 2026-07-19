Set-Location $PSScriptRoot\..
matlab -batch "addpath(fullfile(pwd,'matlab_bridge')); RUN_MISSION_04B_AXIS1D_INTEGRATED_SELFTEST_R2023B"
