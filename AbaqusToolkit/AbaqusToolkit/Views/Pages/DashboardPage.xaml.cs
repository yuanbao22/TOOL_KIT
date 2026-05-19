using Microsoft.Extensions.DependencyInjection;
using AbaqusToolkit.ViewModels.Pages;

namespace AbaqusToolkit.Views.Pages;

public partial class DashboardPage
{
    public DashboardPage()
    {
        InitializeComponent();
        DataContext = App.Services.GetRequiredService<DashboardViewModel>();
    }
}
