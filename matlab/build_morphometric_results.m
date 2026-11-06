function out = build_morphometric_results(varargin)
%BUILD_MORPHOMETRIC_RESULTS  Morphometric features per ROI + weighted means.
%
%   out = build_morphometric_results('convert_run', RUN, 'mask_dir', MASKS, ...
%                                    'out_dir', OUT, ...)
%
%   Input is a run folder of `cmjsc convert` (cell_segmentations/,
%   cellseg_labels.tsv, PROVENANCE.json). For EVERY converted ROI one feature
%   row is computed (extract_morphometric_features.m) and written to
%   OUT/feature_vector_csv/<roi>_features.csv (resume: existing files are
%   skipped). The exclude list (include_row in cellseg_labels.tsv) is applied
%   only for the weighting, exactly like JBA_TA calculate_wmean.m: groups
%   (brain_id, section_number, OST_label, OST_id, side), weight = mask area
%   in pixels.
%
%   Name-Value:
%     'convert_run'      (required) cmjsc convert run folder
%     'mask_dir'         (required) high_resolution_ROIs_masks
%     'out_dir'          (required) e.g. <analysis>/04_morphometry/runs/<YYYYMMDD_HHMM>_morphometry
%     'percentile_trim'  [1 1] (default, as Thalamus) | [] | [low high]
%     'pixel_size_mm'    0.001
%     'texture_weighted' '' | weighted_results_all_included_sections.xlsx
%                        (rows are put in the texture order + join diagnostics)
%     'parallel'         false
%     'project'          ''
%     'allow_dirty'      false (refuse to run from a repo with uncommitted changes)
%     'exclude_list'     '' | JBA_TA exclude list (.xlsx). If given, include_row
%                        is taken from this list (matched by brain_id, section_number,
%                        OST_id, OST_label, side, trace) instead of cellseg_labels.tsv,
%                        e.g. a newer _edit list. Unmatched ROIs get include_row 0.
%
%   Outputs in OUT: feature_vector_csv/, morphometric_results/
%   {all_morphometric_features, weighted_morphometric_results}.{csv,xlsx},
%   label_summary.csv, extraction_inventory.csv, weighted_join_diagnostics.csv,
%   PROVENANCE.json/.md, logs/. A line is appended to registry/runs.tsv.

p = inputParser;
addParameter(p, 'convert_run', '', @(x) ischar(x) || isstring(x));
addParameter(p, 'mask_dir', '', @(x) ischar(x) || isstring(x));
addParameter(p, 'out_dir', '', @(x) ischar(x) || isstring(x));
addParameter(p, 'percentile_trim', [1 1], @(x) isempty(x) || (isnumeric(x) && numel(x)==2));
addParameter(p, 'pixel_size_mm', 0.001);
addParameter(p, 'texture_weighted', '', @(x) ischar(x) || isstring(x));
addParameter(p, 'parallel', false);
addParameter(p, 'project', '', @(x) ischar(x) || isstring(x));
addParameter(p, 'allow_dirty', false);
addParameter(p, 'exclude_list', '', @(x) ischar(x) || isstring(x));
parse(p, varargin{:});
o = p.Results;
o.convert_run = char(o.convert_run); o.mask_dir = char(o.mask_dir); o.out_dir = char(o.out_dir);
assert(~isempty(o.convert_run) && ~isempty(o.mask_dir) && ~isempty(o.out_dir), ...
    'convert_run, mask_dir and out_dir are required.');

repo = fileparts(fileparts(mfilename('fullpath')));
git = local_git(repo);
if git.dirty && ~o.allow_dirty
    error('build_morphometric_results:dirty', ...
        'Repository %s has uncommitted changes (%s). Commit first or pass ''allow_dirty'', true.', repo, git.dirty_files);
end
fv_dir = fullfile(o.out_dir, 'feature_vector_csv');
res_dir = fullfile(o.out_dir, 'morphometric_results');
log_dir = fullfile(o.out_dir, 'logs');
cellfun(@(d) mkdir_if(d), {o.out_dir, fv_dir, res_dir, log_dir});
flog = fopen(fullfile(log_dir, ['build_' datestr(now, 'yyyymmdd_HHMMSS') '.log']), 'a');
c1 = onCleanup(@() fclose(flog));
t0 = tic;
L = readtable(fullfile(o.convert_run, 'cellseg_labels.tsv'), 'FileType', 'text', ...
    'Delimiter', '\t', 'TextType', 'string');
for v = {'roi_stem','brain_id','section_number','OST_id','OST_label','side'}
    L.(v{1}) = string(L.(v{1}));
end
if ~isempty(char(o.exclude_list))
    E = readtable(char(o.exclude_list), 'TextType', 'string');
    for v = {'brain_id','section_number','OST_id','OST_label','side'}
        E.(v{1}) = string(E.(v{1}));
    end
    kE = E.brain_id + "|" + E.section_number + "|" + E.OST_id + "|" + E.OST_label + "|" + E.side + "|" + string(E.trace);
    kL = L.brain_id + "|" + L.section_number + "|" + L.OST_id + "|" + L.OST_label + "|" + L.side + "|" + string(L.trace);
    [tf, loc] = ismember(kL, kE);
    old = L.include_row;
    L.include_row = zeros(height(L), 1);
    L.include_row(tf) = E.include_row(loc(tf));
    logm(flog, sprintf('include_row from %s: %d matched, %d not in list (-> 0), %d changed vs. convert run', ...
        char(o.exclude_list), sum(tf), sum(~tf), sum(L.include_row ~= old)));
end
n = height(L);
logm(flog, sprintf('cmjsc morphometry | repo %s (%s) | convert run %s | %d ROIs | trim %s', ...
    git.describe, git.commit, o.convert_run, n, mat2str(o.percentile_trim)));

seg_dir = fullfile(o.convert_run, 'cell_segmentations');
errs = strings(n, 1); stat = strings(n, 1);
todo = true(n, 1);
for i = 1:n
    if isfile(fullfile(fv_dir, L.roi_stem(i) + "_features.csv")), todo(i) = false; stat(i) = "cached"; end
end
logm(flog, sprintf('cached %d, to compute %d', sum(~todo), sum(todo)));
pt = o.percentile_trim; px = o.pixel_size_mm; mdir = o.mask_dir;
if o.parallel
    parfor i = 1:n
        if ~todo(i), continue; end
        [stat(i), errs(i)] = one(L(i,:), seg_dir, mdir, fv_dir, pt, px);
    end
else
    for i = 1:n
        if ~todo(i), continue; end
        [stat(i), errs(i)] = one(L(i,:), seg_dir, mdir, fv_dir, pt, px);
        if mod(i, 50) == 0, logm(flog, sprintf('  %d / %d (%.0f s)', i, n, toc(t0))); end
    end
end
inv = table(L.roi_stem, stat, errs, 'VariableNames', {'roi_stem','status','message'});
writetable(inv, fullfile(res_dir, 'extraction_inventory.csv'));
logm(flog, sprintf('computed ok %d, failed %d', sum(stat == "ok"), sum(stat == "error")));

% ---- all features -------------------------------------------------------
files = dir(fullfile(fv_dir, '*_features.csv'));
parts = cell(numel(files), 1);
for k = 1:numel(files)
    parts{k} = readtable(fullfile(files(k).folder, files(k).name), 'TextType', 'string', ...
        'VariableNamingRule', 'preserve');
end
F = vertcat(parts{:});
for v = {'roi_stem','brain_id','section_number','OST_id','OST_label','side'}
    F.(v{1}) = string(F.(v{1}));
end
writetable(F, fullfile(res_dir, 'all_morphometric_features.csv'));
try, writetable(F, fullfile(res_dir, 'all_morphometric_features.xlsx')); catch, end

% include_row as used for THIS run (also when taken from 'exclude_list')
[tfI, locI] = ismember(F.roi_stem, L.roi_stem);
F.include_row(tfI) = L.include_row(locI(tfI));
z = F.roi_stem(F.n_cells == 0 & F.include_row == 1);
if ~isempty(z)
    logm(flog, sprintf('WARNING: %d included ROI(s) without any cell: %s', numel(z), strjoin(z, ', ')));
end
% ---- weighted mean (calculate_wmean logic) --------------------------------
Fi = F(F.include_row == 1, :);
logm(flog, sprintf('include_row filter: %d -> %d rows', height(F), height(Fi)));
G = findgroups(Fi.brain_id, Fi.section_number, Fi.OST_label, Fi.OST_id, Fi.side);
is_num = varfun(@isnumeric, Fi, 'OutputFormat', 'uniform');
fcols = setdiff(Fi.Properties.VariableNames(is_num), ...
    {'side_num','trace','n_before_trim','n_after_trim','include_row','mask_area_px'}, 'stable');
nG = max([G; 0]);
W = table('Size', [nG 6], 'VariableTypes', {'string','string','string','string','string','double'}, ...
    'VariableNames', {'brain_id','section_number','OST_label','OST_id','side','area'});
X = nan(nG, numel(fcols)); gs = zeros(nG, 1);
for g = 1:nG
    sub = Fi(G == g, :); gs(g) = height(sub);
    W.brain_id(g) = sub.brain_id(1); W.section_number(g) = sub.section_number(1);
    W.OST_label(g) = sub.OST_label(1); W.OST_id(g) = sub.OST_id(1); W.side(g) = sub.side(1);
    W.area(g) = mean(sub.mask_area_px, 'omitnan');
    w = sub.mask_area_px;
    for c = 1:numel(fcols)
        v = sub.(fcols{c}); m = isfinite(v) & isfinite(w) & w > 0;
        if any(m), X(g, c) = sum(v(m) .* w(m)) / sum(w(m)); end
    end
end
W = [W, array2table(X, 'VariableNames', fcols)];
W.n_group_members = gs;
diag = table();
if ~isempty(o.texture_weighted) && isfile(o.texture_weighted)
    Tt = readtable(o.texture_weighted, 'TextType', 'string', 'VariableNamingRule', 'preserve');
    kt = key5(Tt); km = key5(W);
    [tf, loc] = ismember(kt, km);
    order = [loc(tf); setdiff((1:height(W))', loc(tf))];
    W = W(order, :);
    status = repmat("only_morphometry", height(W), 1);
    status(1:sum(tf)) = "match";
    diag = table(key5(W), status, 'VariableNames', {'key', 'status'});
    diag = [diag; table(kt(~tf), repmat("only_texture", sum(~tf), 1), 'VariableNames', {'key','status'})];
    writetable(diag, fullfile(res_dir, 'weighted_join_diagnostics.csv'));
    logm(flog, sprintf('texture join: %d match, %d only morphometry, %d only texture', ...
        sum(tf), height(W) - sum(tf), sum(~tf)));
end
writetable(W, fullfile(res_dir, 'weighted_morphometric_results.csv'));
try, writetable(W, fullfile(res_dir, 'weighted_morphometric_results.xlsx')); catch, end

% ---- summary per OST_label -------------------------------------------------
S = groupsummary(W, 'OST_label', {'mean','std'}, fcols);
writetable(S, fullfile(res_dir, 'label_summary.csv'));

% ---- provenance + registry --------------------------------------------------
cp = fullfile(o.convert_run, 'PROVENANCE.json');
prov = struct();
prov.run_id = local_leaf(o.out_dir);
prov.tool = 'cmjsc build_morphometric_results (MATLAB)';
prov.finished = char(datetime('now', 'TimeZone', 'local', 'Format', 'yyyy-MM-dd''T''HH:mm:ssZ'));
prov.git = git;
prov.matlab = version;
prov.toolboxes = arrayfun(@(t) sprintf('%s %s', t.Name, t.Version), ver, 'UniformOutput', false);
prov.host = getenv('COMPUTERNAME'); prov.user = getenv('USERNAME');
prov.inputs = struct('convert_run', o.convert_run, 'convert_provenance', cp, ...
    'convert_provenance_sha256', local_sha256(cp), 'mask_dir', o.mask_dir, ...
    'texture_weighted', o.texture_weighted, 'texture_weighted_sha256', local_sha256(o.texture_weighted), ...
    'exclude_list', char(o.exclude_list), 'exclude_list_sha256', local_sha256(char(o.exclude_list)));
prov.parameters = struct('percentile_trim', o.percentile_trim, 'pixel_size_mm', o.pixel_size_mm, ...
    'weight', 'mask_area_px', 'groups', 'brain_id,section_number,OST_label,OST_id,side', ...
    'positions', 'skimage centroid (x_px, y_px)');
prov.summary = struct('rois', n, 'computed_ok', sum(stat == "ok"), 'cached', sum(stat == "cached"), ...
    'failed', sum(stat == "error"), 'rows_all', height(F), 'rows_weighted', height(W), ...
    'seconds', round(toc(t0)));
fid = fopen(fullfile(o.out_dir, 'PROVENANCE.json'), 'w'); fwrite(fid, jsonencode(prov, 'PrettyPrint', true)); fclose(fid);
md = sprintf(['# PROVENANCE – %s\n\n- Tool: %s\n- Repo: %s (%s), dirty %d\n- MATLAB %s\n- Convert run: %s (PROVENANCE sha256 %s)\n' ...
    '- Masks: %s\n- Trim: %s, pixel %g mm, weight mask_area_px\n- ROIs %d: ok %d, cached %d, failed %d; weighted rows %d\n- Finished: %s\n'], ...
    prov.run_id, prov.tool, git.describe, git.commit, git.dirty, prov.matlab, o.convert_run, ...
    prov.inputs.convert_provenance_sha256, o.mask_dir, mat2str(o.percentile_trim), o.pixel_size_mm, ...
    n, prov.summary.computed_ok, prov.summary.cached, prov.summary.failed, height(W), prov.finished);
fid = fopen(fullfile(o.out_dir, 'PROVENANCE.md'), 'w'); fwrite(fid, md); fclose(fid);
reg = fullfile(repo, 'registry', 'runs.tsv');
fid = fopen(reg, 'a');
fprintf(fid, '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%d\t%d\t%s\n', prov.run_id, prov.finished, ...
    'cmjsc morphometry', char(o.project), '', o.out_dir, o.convert_run, git.commit, git.describe, ...
    sprintf('trim %s', mat2str(o.percentile_trim)), '', sum(stat ~= "error"), sum(stat == "error"), '');
fclose(fid);
logm(flog, sprintf('done in %.0f s -> %s', toc(t0), o.out_dir));
out = struct('all_features', F, 'weighted', W, 'out_dir', o.out_dir, 'provenance', prov);
end

function [st, msg] = one(row, seg_dir, mask_dir, fv_dir, pt, px)
st = "ok"; msg = "";
try
    stem = row.roi_stem(1);
    tsv = fullfile(seg_dir, stem + "_CellInstances.tsv.gz");
    mask = fullfile(mask_dir, stem + "_mask.tif");
    if ~isfile(mask)   % JBA_TA special trace: <roi>_special_trace_mask.tif (KI-003)
        alt = fullfile(mask_dir, stem + "_special_trace_mask.tif");
        if isfile(alt), mask = alt; end
    end
    feat = extract_morphometric_features(tsv, mask, row, 'percentile_trim', pt, 'pixel_size_mm', px);
    writetable(feat, fullfile(fv_dir, stem + "_features.csv"));
catch ME
    st = "error"; msg = string(ME.message);
end
end

function k = key5(T)
k = string(T.brain_id) + "|" + string(T.section_number) + "|" + string(T.OST_label) + "|" + ...
    string(T.OST_id) + "|" + string(T.side);
end

function g = local_git(repo)
[~, c] = system(sprintf('git -C "%s" rev-parse HEAD', repo));
[~, d] = system(sprintf('git -C "%s" describe --tags --always --dirty', repo));
[~, r] = system(sprintf('git -C "%s" config --get remote.origin.url', repo));
[~, s] = system(sprintf('git -C "%s" status --porcelain', repo));
% porcelain lines are 'XY path'; do not trim (leading space = status code, KI-001)
lines = splitlines(string(s));
lines = lines(strlength(lines) > 3);
lines = lines(~startsWith(extractAfter(lines, 3), "registry/"));
g = struct('repo', repo, 'commit', strtrim(c), 'describe', strtrim(d), 'remote', strtrim(r), ...
    'dirty', ~isempty(lines), 'dirty_files', strjoin(lines, ', '));
end

function h = local_sha256(f)
h = '';
if isempty(f) || ~isfile(f), return; end
md = java.security.MessageDigest.getInstance('SHA-256');
fid = fopen(f, 'r'); c = onCleanup(@() fclose(fid));
while true
    b = fread(fid, 8*2^20, '*uint8');
    if isempty(b), break; end
    md.update(b);
end
h = lower(reshape(dec2hex(typecast(md.digest(), 'uint8'), 2)', 1, []));
end

function s = local_leaf(p)
[~, a, b] = fileparts(p); s = [a b];
end

function mkdir_if(d)
if ~isfolder(d), mkdir(d); end
end

function logm(fid, msg)
line = sprintf('%s  %s', datestr(now, 'yyyy-mm-dd HH:MM:SS'), msg);
fprintf('%s\n', line); fprintf(fid, '%s\n', line);
end
