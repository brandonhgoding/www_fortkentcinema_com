from django.db import migrations


def remove_cdn_prefix(apps, schema_editor):
    BlogPost = apps.get_model("blog", "BlogPost")
    prefix = "https://cdn.fortkentcinema.com/"
    for post in BlogPost.objects.all():
        if post.header_image and post.header_image.startswith(prefix):
            post.header_image = post.header_image[len(prefix) :]
            post.save(update_fields=["header_image"])


class Migration(migrations.Migration):

    dependencies = [
        ("blog", "0013_alter_blogcategory_slug"),
    ]

    operations = [
        migrations.RunPython(remove_cdn_prefix),
    ]
