using System.Windows.Input;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Microsoft.Win32;
using AbaqusToolkit.Services;

namespace AbaqusToolkit.ViewModels.Pages;

public partial class InpMergeViewModel : ObservableObject
{
    private readonly IInpMergeService _mergeService;

    [ObservableProperty]
    private string _file1Path = string.Empty;

    [ObservableProperty]
    private string _file2Path = string.Empty;

    [ObservableProperty]
    private string _outputPath = string.Empty;

    [ObservableProperty]
    private string _mergeLog = string.Empty;

    [ObservableProperty]
    private bool _isMerging;

    [ObservableProperty]
    private string _statusMessage = "Ready";

    public bool CanMerge => !IsMerging;

    partial void OnIsMergingChanged(bool value)
    {
        OnPropertyChanged(nameof(CanMerge));
    }

    public InpMergeViewModel(IInpMergeService mergeService)
    {
        _mergeService = mergeService;
        _outputPath = System.IO.Path.Combine(
            System.AppDomain.CurrentDomain.BaseDirectory,
            "Job-Merged.inp");
    }

    [RelayCommand]
    private void BrowseFile1()
    {
        var dialog = new OpenFileDialog
        {
            Filter = "Abaqus INP files (*.inp)|*.inp|All files (*.*)|*.*",
            Title = "选择 Job-1 INP 文件"
        };
        if (dialog.ShowDialog() == true)
            File1Path = dialog.FileName;
    }

    [RelayCommand]
    private void BrowseFile2()
    {
        var dialog = new OpenFileDialog
        {
            Filter = "Abaqus INP files (*.inp)|*.inp|All files (*.*)|*.*",
            Title = "选择 Job-2 INP 文件"
        };
        if (dialog.ShowDialog() == true)
            File2Path = dialog.FileName;
    }

    [RelayCommand]
    private void BrowseOutput()
    {
        var dialog = new SaveFileDialog
        {
            Filter = "Abaqus INP files (*.inp)|*.inp|All files (*.*)|*.*",
            Title = "选择输出 INP 文件",
            FileName = "Job-Merged.inp"
        };
        if (dialog.ShowDialog() == true)
            OutputPath = dialog.FileName;
    }

    [RelayCommand]
    private async Task Merge()
    {
        if (string.IsNullOrEmpty(File1Path) || string.IsNullOrEmpty(File2Path))
        {
            StatusMessage = "请选择两个输入文件";
            return;
        }

        IsMerging = true;
        StatusMessage = "正在合并...";
        MergeLog = string.Empty;

        var progress = new Progress<string>(msg =>
        {
            MergeLog += msg + Environment.NewLine;
        });

        var result = await _mergeService.MergeAsync(
            File1Path, File2Path, OutputPath, progress);

        StatusMessage = result.Success
            ? $"Complete -> {OutputPath}"
            : $"Failed: {result.Message}";
        IsMerging = false;
    }
}
