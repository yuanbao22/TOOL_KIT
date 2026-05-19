using System.Configuration;
using System.Data;
using System;
using System.IO;
using System.Windows;
using Microsoft.Extensions.DependencyInjection;
using Serilog;

namespace AbaqusToolkit;

public partial class App : Application
{
    public static IServiceProvider Services =>
        ((App)Current)._serviceProvider;

    private IServiceProvider _serviceProvider = null!;

    protected override void OnStartup(StartupEventArgs e)
    {
        var logDir = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "logs");
        Directory.CreateDirectory(logDir);

        Log.Logger = new LoggerConfiguration()
            .MinimumLevel.Debug()
            .WriteTo.Console()
            .WriteTo.File(
                Path.Combine(logDir, "abaqus-toolkit-.log"),
                rollingInterval: RollingInterval.Day,
                retainedFileCountLimit: 14)
            .CreateLogger();

        try
        {
            Log.Information("AbaqusToolkit starting...");

            var services = new ServiceCollection();
            ConfigureServices(services);
            _serviceProvider = services.BuildServiceProvider();

            base.OnStartup(e);
        }
        catch (Exception ex)
        {
            Log.Fatal(ex, "Application failed to start");
            MessageBox.Show($"Application failed to start:\n{ex.Message}", "Error",
                MessageBoxButton.OK, MessageBoxImage.Error);
            Shutdown();
        }
    }

    private static void ConfigureServices(IServiceCollection services)
    {
        services.AddSingleton<Services.IInpMergeService, Services.InpMergeService>();
        services.AddSingleton<MainWindow>();
        services.AddTransient<ViewModels.MainViewModel>();
        services.AddTransient<ViewModels.Pages.DashboardViewModel>();
        services.AddTransient<ViewModels.Pages.InpMergeViewModel>();
    }

    protected override void OnExit(ExitEventArgs e)
    {
        Log.CloseAndFlush();
        base.OnExit(e);
    }
}

