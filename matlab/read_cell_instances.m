function T = read_cell_instances(tsv_file)
%READ_CELL_INSTANCES  Read <roi>_CellInstances.tsv(.gz) written by cmjsc convert.
%   T = READ_CELL_INSTANCES(FILE) returns a table, one row per cell. Column
%   names are kept as written (e.g. cell_area_px, x_px, y_px).
tsv_file = char(tsv_file);
if endsWith(tsv_file, '.gz')
    tmp = tempname; mkdir(tmp);
    c = onCleanup(@() rmdir(tmp, 's'));
    f = gunzip(tsv_file, tmp);
    src = f{1};
else
    src = tsv_file;
end
opts = detectImportOptions(src, 'FileType', 'text', 'Delimiter', '\t', ...
    'VariableNamingRule', 'preserve');
T = readtable(src, opts);
% KI-002: a ROI without cells gives an empty table whose columns MATLAB reads
% as text; make every column numeric so downstream code works unchanged.
if height(T) == 0
    for v = T.Properties.VariableNames
        T.(v{1}) = zeros(0, 1);
    end
end
end
