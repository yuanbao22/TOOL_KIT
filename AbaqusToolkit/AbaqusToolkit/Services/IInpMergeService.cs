namespace AbaqusToolkit.Services;

public interface IInpMergeService
{
    Task<MergeResult> MergeAsync(
        string file1Path,
        string file2Path,
        string outputPath,
        IProgress<string>? progress = null,
        CancellationToken ct = default);
}
