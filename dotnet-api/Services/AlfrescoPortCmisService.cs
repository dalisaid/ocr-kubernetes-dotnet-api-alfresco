using PortCMIS;
using PortCMIS.Client;
using PortCMIS.Client.Impl;

public class AlfrescoPortCmisService
{
    private readonly PortCMIS.Client.ISession _session;
    private readonly IConfiguration _config;


    public AlfrescoPortCmisService(IConfiguration config)



    {
        _config = config;
        var factory = SessionFactory.NewInstance();

        var parameters = new Dictionary<string, string>
        {
            [SessionParameter.BindingType] = BindingType.Browser,
            [SessionParameter.BrowserUrl] = $"{config["Alfresco:BaseUrl"]}/alfresco/api/-default-/public/cmis/versions/1.1/browser",
            [SessionParameter.PreemptivAuthentication] = "true",
            [SessionParameter.User] = config["Alfresco:Username"]?? throw new InvalidOperationException("Username not configured IN CMIS"),
            [SessionParameter.Password] = config["Alfresco:Password"]?? throw new InvalidOperationException("Password not configured in CMIS")
        };

        _session = factory.GetRepositories(parameters)[0].CreateSession();
    }

    public PortCMIS.Client.ISession Session => _session;


    public byte[] ImageStream(IDocument doc)// no longer in use switched to  urls for file streaming
    {
        byte[] filebytes;
        using (var stream = doc.GetContentStream().Stream)
        using (var memoryStream = new MemoryStream())
        {
            stream.CopyTo(memoryStream);
            filebytes = memoryStream.ToArray();
        }
        return filebytes;
    }

 


    public List<ClientFolder> GetClientUploads()
    {
        string parentFolderId = _config["Alfresco:FolderNodeId"]
            ?? throw new InvalidOperationException("FolderNodeId not configured in CMIS");

        var parentFolder = (IFolder)_session.GetObject(parentFolderId);
        var uploads = new List<ClientFolder>();

        foreach (var child in parentFolder.GetChildren())
        {
            if (child is IFolder subFolder)
            {


                var upload = new ClientFolder
                {
                    FolderName = subFolder.Name,
                    Title = subFolder.GetPropertyValue("cm:title")?.ToString() ?? "failed to fetch title",
                    Description = subFolder.GetPropertyValue("cm:description")?.ToString() ?? "failed to fetch description"
                };

                foreach (var doc in subFolder.GetChildren().OfType<IDocument>())
                {
                    
                    upload.Files.Add(new ClientFileRecord
                    {
                        FileName = doc.Name,
                        FilePath = $"{subFolder.Name}/{doc.Name}",
                        DownloadUrl = "/api/files/" + Uri.EscapeDataString(doc.Id)
                    });
                }

                uploads.Add(upload);
            }
        }

        return uploads;
    }


    
}
