using Microsoft.Extensions.DependencyInjection;
using AbaqusToolkit.ViewModels.Pages;

namespace AbaqusToolkit.Views.Pages;

public partial class InpMergePage
{
    public InpMergePage()
    {
        InitializeComponent();
        DataContext = App.Services.GetRequiredService<InpMergeViewModel>();
    }
}
