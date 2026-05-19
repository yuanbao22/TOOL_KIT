using HandyControl.Controls;
using HandyControl.Data;

namespace AbaqusToolkit;

public partial class MainWindow
{
    public MainWindow()
    {
        InitializeComponent();
    }

    private void OnNavChanged(object sender, FunctionEventArgs<object> e)
    {
        if (e.Info is SideMenuItem item && item.Tag is string tag)
            NavigateTo(tag);
    }

    private void NavigateTo(string pageKey)
    {
        var uri = pageKey switch
        {
            "Dashboard" => "Views/Pages/DashboardPage.xaml",
            "Merge" => "Views/Pages/InpMergePage.xaml",
            _ => "Views/Pages/DashboardPage.xaml"
        };
        RootFrame.Navigate(new System.Uri(uri, System.UriKind.Relative));
    }
}
